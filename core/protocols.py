from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .schemas import DiffResult, GenerationResult, InterfaceSpec, ValidationResult


@dataclass
class WorkflowContext:
    workspace: Path
    output_dir: Path
    kernel_src: Path | None = None
    syzkaller_dir: Path | None = None
    config: dict[str, object] = field(default_factory=dict)


class DiscoverPlugin(Protocol):
    name: str

    def discover(self, ctx: WorkflowContext) -> list[InterfaceSpec]:
        ...


class DiffPlugin(Protocol):
    name: str

    def diff(self, current: list[InterfaceSpec], existing: object, ctx: WorkflowContext) -> DiffResult:
        ...


class GeneratePlugin(Protocol):
    name: str

    def generate(self, diff: DiffResult, ctx: WorkflowContext) -> GenerationResult:
        ...


class ValidatePlugin(Protocol):
    name: str

    def validate(self, generation: GenerationResult, ctx: WorkflowContext) -> ValidationResult:
        ...
