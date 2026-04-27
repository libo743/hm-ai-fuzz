from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from core.pipeline import WorkflowPipeline, write_json
from core.protocols import WorkflowContext
from core.schema_adapter_v2 import (
    adapt_diff_proc_v2,
    adapt_discover_proc_v2,
    adapt_generate_proc_v2,
    adapt_validate_proc_v2,
    diff_v2_to_diff_result,
)
from extractors.proc.extractor import ProcDiscoverPlugin
from generators.syzkaller.minimal import MinimalSyzkallerGeneratePlugin
from llm.agents.discover_agent import DiscoverAgent
from llm.agents.fix_agent import FixAgent
from llm.agents.model_agent import ModelAgent
from llm.client import LLMClient
from llm.config import load_config_from_env
from modelers.simple_diff import SimpleDiffPlugin
from validators.syzkaller_build import SyzkallerBuildValidatePlugin

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTERNAL_ROOT = REPO_ROOT.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hm-ai-fuzz",
        description="Plugin-based scaffold workflow for future syscall fuzz generation",
    )
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="project workspace")
    parser.add_argument("--kernel-src", type=Path, default=DEFAULT_EXTERNAL_ROOT / "linux", help="Linux source root")
    parser.add_argument("--syzkaller-dir", type=Path, default=DEFAULT_EXTERNAL_ROOT / "syzkaller", help="syzkaller root")
    parser.add_argument("--target-module", default="fs/proc", help="subsystem module scope")
    parser.add_argument("--search-method", choices=("exact", "prefix", "substring"), default="prefix")
    parser.add_argument("--scan-mode", choices=("auto", "full"), default="auto")
    parser.add_argument("--out-dir", type=Path, default=Path("out"), help="output directory")
    parser.add_argument("--existing-json", type=Path, help="optional baseline json")
    parser.add_argument("--out-json", type=Path, default=Path("out/workflow-result.json"), help="workflow result json")
    parser.add_argument("--make-target", default="descriptions")
    parser.add_argument("--timeout-sec", type=int, default=300)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    existing = {}
    if args.existing_json and args.existing_json.is_file():
        existing = json.loads(args.existing_json.read_text(encoding="utf-8"))

    ctx = WorkflowContext(
        workspace=args.workspace.resolve(),
        output_dir=args.out_dir.resolve(),
        kernel_src=args.kernel_src.resolve(),
        syzkaller_dir=args.syzkaller_dir.resolve(),
        config={
            "target_module": args.target_module,
            "search_method": args.search_method,
            "scan_mode": args.scan_mode,
            "txt_name": "proc_auto.txt",
            "make_target": args.make_target,
            "timeout_sec": args.timeout_sec,
        },
    )
    pipeline = WorkflowPipeline(
        discover_plugin=ProcDiscoverPlugin(),
        diff_plugin=SimpleDiffPlugin(),
        generate_plugin=MinimalSyzkallerGeneratePlugin(),
        validate_plugin=SyzkallerBuildValidatePlugin(),
    )
    result = pipeline.run(ctx, existing)
    discover_v2 = adapt_discover_proc_v2(result["discover"], ctx)
    diff_v2 = adapt_diff_proc_v2(result["diff"], discover_v2)
    generate_plugin = MinimalSyzkallerGeneratePlugin()
    validate_plugin = SyzkallerBuildValidatePlugin()
    generation_v2_raw = generate_plugin.generate(diff_v2_to_diff_result(diff_v2), ctx)
    generate_v2 = adapt_generate_proc_v2(generation_v2_raw, diff_v2)
    validate_v2 = adapt_validate_proc_v2(validate_plugin.validate(generation_v2_raw, ctx))
    publish = _build_publish_summary(generation_v2_raw, validate_v2, ctx)
    llm_config = load_config_from_env()
    llm_client = LLMClient(llm_config)
    prompt_dir = ctx.workspace / "llm" / "prompts"
    discover_suggestions = {
        "enabled": llm_config.enabled and llm_config.features.discover_enhance,
        "status": "skipped",
        "reason": "discover_enhance feature is disabled",
        "suggestions": [],
    }
    if llm_config.features.discover_enhance:
        discover_suggestions = _run_discover_agent_side_channel(
            discover_v2=discover_v2,
            ctx=ctx,
            client=llm_client,
            prompt_dir=prompt_dir,
            llm_enabled=llm_config.enabled,
            limit=_env_int("HM_AI_FUZZ_LLM_DISCOVER_LIMIT"),
        )
    model_suggestions = {
        "enabled": llm_config.enabled and llm_config.features.model_enhance,
        "status": "skipped",
        "reason": "model_enhance feature is disabled",
        "suggestions": [],
    }
    if llm_config.features.model_enhance:
        model_suggestions = _run_model_agent_side_channel(
            diff_v2=diff_v2,
            ctx=ctx,
            client=llm_client,
            prompt_dir=prompt_dir,
            llm_enabled=llm_config.enabled,
            limit=_env_int("HM_AI_FUZZ_LLM_MODEL_LIMIT"),
        )
    fix_suggestions = {
        "enabled": llm_config.enabled and llm_config.features.fix_suggest,
        "status": "skipped",
        "reason": "fix_suggest feature is disabled",
        "suggestions": [],
    }
    if llm_config.features.fix_suggest:
        fix_agent = FixAgent(llm_client, prompt_dir)
        failed_unit = _select_failed_unit(generate_v2, validate_v2)
        source_fragment = _source_fragment_for_failed_unit(generate_v2, ctx)
        try:
            suggestion = fix_agent.suggest(
                validate_v2=validate_v2,
                failed_unit=failed_unit,
                source_fragment=source_fragment,
            )
            fix_suggestions = {
                "enabled": llm_config.enabled,
                "status": "ok",
                "reason": None,
                "suggestions": [suggestion],
            }
        except Exception as exc:
            fix_suggestions = {
                "enabled": llm_config.enabled,
                "status": "error",
                "reason": str(exc),
                "suggestions": [],
            }
    result["discover_v2"] = discover_v2
    result["diff_v2"] = diff_v2
    result["generate_v2"] = generate_v2
    result["validate_v2"] = validate_v2
    result["publish"] = publish
    result["llm_discover_suggestions"] = discover_suggestions
    result["llm_model_suggestions"] = model_suggestions
    result["llm_fix_suggestions"] = fix_suggestions
    output_dir = args.out_dir.resolve()
    write_json(output_dir / "discover.json", result["discover"])
    write_json(output_dir / "discover-v2.json", discover_v2)
    write_json(output_dir / "diff.json", result["diff"])
    write_json(output_dir / "diff-v2.json", diff_v2)
    write_json(output_dir / "generate.json", result["generate"])
    write_json(output_dir / "generate-v2.json", generate_v2)
    write_json(output_dir / "validate.json", result["validate"])
    write_json(output_dir / "validate-v2.json", validate_v2)
    write_json(output_dir / "publish.json", publish)
    write_json(output_dir / "llm" / "discover-suggestions.json", discover_suggestions)
    write_json(output_dir / "llm" / "model-suggestions.json", model_suggestions)
    write_json(output_dir / "llm" / "fix-suggestions.json", fix_suggestions)
    write_json(args.out_json.resolve(), result)
    print(f"workflow result: {args.out_json.resolve()}")
    return 0


def _run_discover_agent_side_channel(
    *,
    discover_v2: dict[str, Any],
    ctx: WorkflowContext,
    client: LLMClient,
    prompt_dir: Path,
    llm_enabled: bool,
    limit: int | None,
) -> dict[str, Any]:
    agent = DiscoverAgent(client, prompt_dir)
    suggestions: list[dict[str, Any]] = []
    try:
        items = discover_v2.get("items", [])
        if not isinstance(items, list):
            items = []
        if isinstance(limit, int) and limit > 0:
            items = items[:limit]
        for item in items:
            if not isinstance(item, dict):
                continue
            snippets = _snippets_for_item_source(item, ctx)
            suggestions.append(agent.suggest(item=item, snippets=snippets))
    except Exception as exc:
        return {
            "enabled": llm_enabled,
            "status": "error",
            "reason": str(exc),
            "suggestions": suggestions,
        }
    return {
        "enabled": llm_enabled,
        "status": "ok",
        "reason": None,
        "suggestions": suggestions,
    }


def _run_model_agent_side_channel(
    *,
    diff_v2: dict[str, Any],
    ctx: WorkflowContext,
    client: LLMClient,
    prompt_dir: Path,
    llm_enabled: bool,
    limit: int | None,
) -> dict[str, Any]:
    agent = ModelAgent(client, prompt_dir)
    suggestions: list[dict[str, Any]] = []
    try:
        items = diff_v2.get("new_items", [])
        if not isinstance(items, list):
            items = []
        if isinstance(limit, int) and limit > 0:
            items = items[:limit]
        for item in items:
            if not isinstance(item, dict):
                continue
            snippets = _snippets_for_item_source(item, ctx)
            item_key = item.get("item_key")
            if not isinstance(item_key, str):
                continue
            suggestions.append(
                agent.suggest(
                    item_key=item_key,
                    diff_item=item,
                    snippets=snippets,
                    structs=[],
                )
            )
    except Exception as exc:
        return {
            "enabled": llm_enabled,
            "status": "error",
            "reason": str(exc),
            "suggestions": suggestions,
        }
    return {
        "enabled": llm_enabled,
        "status": "ok",
        "reason": None,
        "suggestions": suggestions,
    }


def _snippets_for_item_source(item: dict[str, Any], ctx: WorkflowContext) -> list[dict[str, str]]:
    source = item.get("source")
    if not isinstance(source, dict):
        return []
    file_name = source.get("file")
    if not isinstance(file_name, str) or not file_name or ctx.kernel_src is None:
        return []
    path = ctx.kernel_src / file_name
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    line_no = source.get("line")
    symbol = source.get("symbol")
    snippet = _slice_source_text(text, line_no if isinstance(line_no, int) else None)
    return [
        {
            "file": str(path),
            "line": str(line_no) if isinstance(line_no, int) else "",
            "symbol": symbol if isinstance(symbol, str) else "",
            "code": snippet,
        }
    ]


def _slice_source_text(text: str, line_no: int | None, radius: int = 20, max_chars: int = 4000) -> str:
    lines = text.splitlines()
    if not lines:
        return ""
    if line_no is None or line_no <= 0 or line_no > len(lines):
        snippet = "\n".join(lines[: min(len(lines), radius * 2)])
    else:
        start = max(0, line_no - 1 - radius)
        end = min(len(lines), line_no - 1 + radius)
        snippet = "\n".join(lines[start:end])
    return snippet[:max_chars]


def _env_int(name: str) -> int | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _build_publish_summary(
    generation: dict[str, Any],
    validate_v2: dict[str, Any],
    ctx: WorkflowContext,
) -> dict[str, Any]:
    generated_files: list[dict[str, Any]] = []
    for item in generation.generated_files:
        path = Path(item.path)
        generated_files.append(
            {
                "path": str(path),
                "kind": item.kind,
                "exists": path.is_file(),
                "repo": "syzkaller" if ctx.syzkaller_dir and _is_relative_to(path, ctx.syzkaller_dir) else "unknown",
            }
        )
    return {
        "schema_version": "v1",
        "target_repo": str(ctx.syzkaller_dir) if ctx.syzkaller_dir is not None else None,
        "target_subdir": str((ctx.syzkaller_dir / "sys" / "linux") if ctx.syzkaller_dir is not None else ""),
        "generated_files": generated_files,
        "validate_status": validate_v2.get("status"),
        "make_target": ctx.config.get("make_target", "descriptions"),
        "published": bool(generated_files) and all(item["exists"] for item in generated_files),
    }


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _select_failed_unit(generate_v2: dict[str, object], validate_v2: dict[str, object]) -> dict[str, object] | None:
    diagnostics = validate_v2.get("diagnostics")
    units = generate_v2.get("generated_units")
    if not isinstance(diagnostics, list) or not isinstance(units, list):
        return None
    symbol_to_unit = {
        str(unit.get("symbol_name")): unit
        for unit in units
        if isinstance(unit, dict) and isinstance(unit.get("symbol_name"), str)
    }
    for diag in diagnostics:
        if not isinstance(diag, dict):
            continue
        item_key = diag.get("item_key")
        if isinstance(item_key, str):
            for unit in units:
                if isinstance(unit, dict) and unit.get("item_key") == item_key:
                    return unit
        failed_symbol = _extract_failed_symbol_from_diagnostic(diag, generate_v2)
        if failed_symbol is not None:
            matched = symbol_to_unit.get(failed_symbol)
            if isinstance(matched, dict):
                return matched
    return units[0] if units and isinstance(units[0], dict) else None


def _extract_failed_symbol_from_diagnostic(
    diagnostic: dict[str, object],
    generate_v2: dict[str, object],
) -> str | None:
    file_name = diagnostic.get("file")
    line_no = diagnostic.get("line")
    if not isinstance(file_name, str) or not isinstance(line_no, int) or line_no <= 0:
        return None
    generated_files = generate_v2.get("generated_files")
    if not isinstance(generated_files, list):
        return None
    for item in generated_files:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        kind = item.get("kind")
        if not isinstance(path, str) or kind != "txt":
            continue
        file_path = Path(path)
        if file_path.name != Path(file_name).name or not file_path.is_file():
            continue
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line_no > len(lines):
            return None
        line = lines[line_no - 1].strip()
        match = re.match(r"([A-Za-z0-9$_]+)\(", line)
        if match:
            return match.group(1)
    return None


def _source_fragment_for_failed_unit(generate_v2: dict[str, object], ctx: WorkflowContext) -> dict[str, object] | None:
    files = generate_v2.get("generated_files")
    if not isinstance(files, list):
        return None
    for item in files:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        kind = item.get("kind")
        if not isinstance(path, str) or kind != "txt":
            continue
        file_path = Path(path)
        if not file_path.is_file():
            continue
        text = file_path.read_text(encoding="utf-8", errors="replace")
        return {
            "file": str(file_path),
            "code": text[:4000],
        }
    return None


if __name__ == "__main__":
    raise SystemExit(main())
