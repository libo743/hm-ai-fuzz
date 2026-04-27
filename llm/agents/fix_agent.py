from __future__ import annotations

from pathlib import Path
from typing import Any

from llm.client import LLMClient
from llm.schemas import validate_fix_suggestion


class FixAgent:
    def __init__(self, client: LLMClient, prompt_dir: Path):
        self.client = client
        self.prompt_dir = prompt_dir

    def suggest(
        self,
        *,
        validate_v2: dict[str, Any],
        failed_unit: dict[str, Any] | None,
        source_fragment: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not self.client.is_available():
            item_key = None
            if isinstance(failed_unit, dict):
                value = failed_unit.get("item_key")
                if isinstance(value, str):
                    item_key = value
            return validate_fix_suggestion(
                {
                    "item_key": item_key or "unknown",
                    "fixes": [],
                    "confidence": "low",
                    "evidence": [],
                    "warnings": ["LLM client is not enabled or api key is missing"],
                }
            )
        system_prompt = (self.prompt_dir / "fix_system.txt").read_text(encoding="utf-8")
        payload = {
            "task": "analyze syzkaller description validation failures and suggest repairs",
            "validate_v2": validate_v2,
            "failed_unit": failed_unit or {},
            "source_fragment": source_fragment or {},
        }
        return validate_fix_suggestion(self.client.json_call(system_prompt=system_prompt, user_payload=payload))
