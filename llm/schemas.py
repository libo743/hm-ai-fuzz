from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SuggestionBase:
    confidence: str = "medium"
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DiscoverSuggestion(SuggestionBase):
    interface_id: str = ""
    suggested_operations: list[str] = field(default_factory=list)


@dataclass
class ModelSuggestion(SuggestionBase):
    item_key: str = ""
    suggestions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FixSuggestion(SuggestionBase):
    item_key: str = ""
    fixes: list[dict[str, Any]] = field(default_factory=list)


def validate_discover_suggestion(payload: dict[str, Any]) -> dict[str, Any]:
    _require_string(payload, "interface_id")
    _require_string_list(payload, "suggested_operations")
    return payload


def validate_model_suggestion(payload: dict[str, Any]) -> dict[str, Any]:
    _require_string(payload, "item_key")
    if not isinstance(payload.get("suggestions"), list):
        raise ValueError("suggestions must be a list")
    return payload


def validate_fix_suggestion(payload: dict[str, Any]) -> dict[str, Any]:
    _require_string(payload, "item_key")
    if not isinstance(payload.get("fixes"), list):
        raise ValueError("fixes must be a list")
    return payload


def _require_string(payload: dict[str, Any], key: str) -> None:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")


def _require_string_list(payload: dict[str, Any], key: str) -> None:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings")
