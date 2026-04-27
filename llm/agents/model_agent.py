from __future__ import annotations

from pathlib import Path
from typing import Any

from llm.client import LLMClient
from llm.schemas import validate_model_suggestion


class ModelAgent:
    def __init__(self, client: LLMClient, prompt_dir: Path):
        self.client = client
        self.prompt_dir = prompt_dir

    def suggest(
        self,
        *,
        item_key: str,
        diff_item: dict[str, Any],
        snippets: list[dict[str, str]],
        structs: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        if not self.client.is_available():
            return validate_model_suggestion(
                {
                    "item_key": item_key or "unknown",
                    "suggestions": [],
                    "confidence": "low",
                    "evidence": [],
                    "warnings": ["LLM client is not enabled or api key is missing"],
                }
            )
        system_prompt = (self.prompt_dir / "model_system.txt").read_text(encoding="utf-8")
        payload = {
            "task": "suggest syzkaller modeling details for a kernel interface operation",
            "item_key": item_key,
            "diff_item": diff_item,
            "snippets": snippets,
            "structs": structs or [],
        }
        return validate_model_suggestion(self.client.json_call(system_prompt=system_prompt, user_payload=payload))
