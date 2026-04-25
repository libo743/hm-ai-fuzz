from __future__ import annotations

import json
from pathlib import Path

from .protocols import DiffPlugin, DiscoverPlugin, GeneratePlugin, ValidatePlugin, WorkflowContext
from .schemas import DiffResult, GenerationResult, ValidationResult, to_jsonable


class WorkflowPipeline:
    def __init__(
        self,
        *,
        discover_plugin: DiscoverPlugin,
        diff_plugin: DiffPlugin,
        generate_plugin: GeneratePlugin,
        validate_plugin: ValidatePlugin,
    ) -> None:
        self.discover_plugin = discover_plugin
        self.diff_plugin = diff_plugin
        self.generate_plugin = generate_plugin
        self.validate_plugin = validate_plugin

    def run(self, ctx: WorkflowContext, existing: object) -> dict[str, object]:
        current = self.discover_plugin.discover(ctx)
        diff: DiffResult = self.diff_plugin.diff(current, existing, ctx)
        generation: GenerationResult = self.generate_plugin.generate(diff, ctx)
        validation: ValidationResult = self.validate_plugin.validate(generation, ctx)
        return {
            "discover": to_jsonable(current),
            "diff": to_jsonable(diff),
            "generate": to_jsonable(generation),
            "validate": to_jsonable(validation),
        }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
