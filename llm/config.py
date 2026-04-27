from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LLMFeatureFlags:
    discover_enhance: bool = False
    model_enhance: bool = False
    fix_suggest: bool = False


@dataclass
class LLMConfig:
    enabled: bool = False
    provider: str = "openai_compatible"
    model: str = "gpt-4.1-mini"
    base_url: str = "https://api.openai.com/v1"
    wire_api: str = "chat_completions"
    api_key_env: str = "HM_AI_FUZZ_API_KEY"
    debug_dir: Path | None = None
    timeout_sec: int = 60
    temperature: float = 0.0
    max_output_tokens: int = 4000
    features: LLMFeatureFlags = field(default_factory=LLMFeatureFlags)

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env)


def load_config_from_env() -> LLMConfig:
    enabled = os.environ.get("HM_AI_FUZZ_LLM_ENABLED", "").lower() in {"1", "true", "yes", "on"}
    return LLMConfig(
        enabled=enabled,
        provider=os.environ.get("HM_AI_FUZZ_LLM_PROVIDER", "openai_compatible"),
        model=os.environ.get("HM_AI_FUZZ_LLM_MODEL", "gpt-4.1-mini"),
        base_url=os.environ.get("HM_AI_FUZZ_LLM_BASE_URL", "https://api.openai.com/v1"),
        wire_api=os.environ.get("HM_AI_FUZZ_LLM_WIRE_API", "chat_completions"),
        api_key_env=os.environ.get("HM_AI_FUZZ_API_KEY_ENV", "HM_AI_FUZZ_API_KEY"),
        debug_dir=Path(value) if (value := os.environ.get("HM_AI_FUZZ_LLM_DEBUG_DIR", "").strip()) else None,
        timeout_sec=int(os.environ.get("HM_AI_FUZZ_LLM_TIMEOUT_SEC", "60")),
        temperature=float(os.environ.get("HM_AI_FUZZ_LLM_TEMPERATURE", "0")),
        max_output_tokens=int(os.environ.get("HM_AI_FUZZ_LLM_MAX_OUTPUT_TOKENS", "4000")),
        features=LLMFeatureFlags(
            discover_enhance=os.environ.get("HM_AI_FUZZ_LLM_DISCOVER_ENHANCE", "").lower() in {"1", "true", "yes", "on"},
            model_enhance=os.environ.get("HM_AI_FUZZ_LLM_MODEL_ENHANCE", "").lower() in {"1", "true", "yes", "on"},
            fix_suggest=os.environ.get("HM_AI_FUZZ_LLM_FIX_SUGGEST", "").lower() in {"1", "true", "yes", "on"},
        ),
    )
