from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.response import addinfourl

from .config import LLMConfig


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config

    def is_available(self) -> bool:
        return self.config.enabled and bool(self.config.api_key)

    def json_call(self, *, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        if not self.is_available():
            raise RuntimeError("LLM client is not enabled or api key is missing")
        if self.config.provider != "openai_compatible":
            raise ValueError(f"unsupported provider: {self.config.provider}")

        wire_api = self.config.wire_api.strip().lower()
        if wire_api == "responses":
            url = self.config.base_url.rstrip("/") + "/responses"
            body = {
                "model": self.config.model,
                "temperature": self.config.temperature,
                "max_output_tokens": self.config.max_output_tokens,
                "stream": True,
                "text": {"format": {"type": "json_object"}},
                "input": [
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": json.dumps(user_payload, ensure_ascii=False),
                    },
                ],
            }
        elif wire_api == "chat_completions":
            url = self.config.base_url.rstrip("/") + "/chat/completions"
            body = {
                "model": self.config.model,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_output_tokens,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
            }
        else:
            raise ValueError(f"unsupported wire_api: {self.config.wire_api}")
        data = json.dumps(body).encode("utf-8")
        debug_base = self._prepare_debug_base()
        if debug_base is not None:
            self._write_debug(debug_base.with_suffix(".request.json"), body)
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_sec) as resp:
                payload, raw_text = _load_payload(resp, wire_api)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if debug_base is not None:
                debug_base.with_suffix(".http-error.txt").write_text(detail, encoding="utf-8")
            raise RuntimeError(f"LLM http error {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            if debug_base is not None:
                debug_base.with_suffix(".url-error.txt").write_text(str(exc), encoding="utf-8")
            raise RuntimeError(f"LLM network error: {exc}") from exc
        if debug_base is not None:
            debug_base.with_suffix(".response.raw.txt").write_text(raw_text, encoding="utf-8")
            self._write_debug(debug_base.with_suffix(".response.payload.json"), payload)

        content = _extract_text_content(payload, wire_api)
        if not isinstance(content, str):
            raise RuntimeError(f"unexpected LLM content type: {type(content)!r}")
        if debug_base is not None:
            debug_base.with_suffix(".response.content.txt").write_text(content, encoding="utf-8")
        parsed = json.loads(content)
        if debug_base is not None:
            self._write_debug(debug_base.with_suffix(".response.parsed.json"), parsed)
        return parsed

    def _prepare_debug_base(self) -> Path | None:
        debug_dir = self.config.debug_dir
        if debug_dir is None:
            return None
        debug_dir.mkdir(parents=True, exist_ok=True)
        return debug_dir / f"llm-{int(time.time() * 1000)}-{os.getpid()}"

    def _write_debug(self, path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _extract_text_content(payload: dict[str, Any], wire_api: str) -> str:
    if wire_api == "chat_completions":
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected LLM response shape: {payload}") from exc
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
            if text_parts:
                return "".join(text_parts)
        raise RuntimeError(f"unexpected chat content shape: {content!r}")

    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = payload.get("output")
    if isinstance(output, list):
        text_parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content_items = item.get("content")
            if not isinstance(content_items, list):
                continue
            for content_item in content_items:
                if not isinstance(content_item, dict):
                    continue
                text = content_item.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
                elif isinstance(content_item.get("output_text"), str):
                    text_parts.append(str(content_item["output_text"]))
        if text_parts:
            return "".join(text_parts)

    raise RuntimeError(f"unexpected LLM response shape: {payload}")


def _load_payload(resp: addinfourl, wire_api: str) -> tuple[dict[str, Any], str]:
    raw = resp.read().decode("utf-8", errors="replace")
    content_type = resp.headers.get("Content-Type", "")
    if wire_api == "responses" and ("text/event-stream" in content_type or raw.lstrip().startswith("event:") or raw.lstrip().startswith("data:")):
        return _parse_sse_payload(raw), raw
    return json.loads(raw), raw


def _parse_sse_payload(raw: str) -> dict[str, Any]:
    output_text_parts: list[str] = []
    last_response: dict[str, Any] | None = None
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if not data_lines:
            continue
        data = "\n".join(data_lines).strip()
        if not data or data == "[DONE]":
            continue
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if event_type == "response.output_text.delta":
            delta = event.get("delta")
            if isinstance(delta, str):
                output_text_parts.append(delta)
        elif event_type == "response.completed":
            response = event.get("response")
            if isinstance(response, dict):
                last_response = response
        elif event_type == "response.output_text.done":
            text = event.get("text")
            if isinstance(text, str) and not output_text_parts:
                output_text_parts.append(text)
        elif "output_text" in event and isinstance(event.get("output_text"), str):
            output_text_parts.append(str(event["output_text"]))
    if output_text_parts:
        return {"output_text": "".join(output_text_parts)}
    if last_response is not None:
        return last_response
    raise RuntimeError(f"unexpected SSE response shape: {raw[:1000]}")
