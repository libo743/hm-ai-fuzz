from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SourceRef:
    file: str
    line: int | None = None
    symbol: str | None = None


@dataclass
class InterfaceSpec:
    subsystem: str
    target: str
    kind: str
    capabilities: list[str] = field(default_factory=list)
    source: SourceRef | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiffResult:
    current: list[InterfaceSpec] = field(default_factory=list)
    existing_keys: list[str] = field(default_factory=list)
    new: list[InterfaceSpec] = field(default_factory=list)
    new_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class GeneratedFile:
    path: str
    kind: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResult:
    generated_files: list[GeneratedFile] = field(default_factory=list)
    units: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    status: str
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {k: to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, Path):
        return str(value)
    return value
