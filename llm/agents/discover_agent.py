from __future__ import annotations

from pathlib import Path
from typing import Any

from llm.client import LLMClient
from llm.schemas import validate_discover_suggestion


class DiscoverAgent:
    def __init__(self, client: LLMClient, prompt_dir: Path):
        self.client = client
        self.prompt_dir = prompt_dir

    def suggest(self, *, item: dict[str, Any], snippets: list[dict[str, str]]) -> dict[str, Any]:
        if not self.client.is_available():
            interface_id = item.get("interface_id")
            if not isinstance(interface_id, str) or not interface_id:
                interface_id = "unknown"
            return validate_discover_suggestion(
                {
                    "interface_id": interface_id,
                    "suggested_operations": [],
                    "confidence": "low",
                    "evidence": [],
                    "warnings": ["LLM client is not enabled or api key is missing"],
                }
            )
        system_prompt = (self.prompt_dir / "discover_system.txt").read_text(encoding="utf-8")
        payload = {
            "task": "analyze kernel interface discovery and suggest missing operations",
            "item": item,
            "snippets": snippets,
        }
        return validate_discover_suggestion(self.client.json_call(system_prompt=system_prompt, user_payload=payload))
