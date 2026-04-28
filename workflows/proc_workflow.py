from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from core.pipeline import write_json
from core.protocols import WorkflowContext
from core.schema_adapter_v2 import (
    adapt_diff_proc_v2,
    adapt_discover_proc_v2,
    adapt_generate_proc_v2,
    adapt_validate_proc_v2,
    diff_v2_to_diff_result,
)
from core.schemas import InterfaceSpec, SourceRef, to_jsonable
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
    discover_plugin = ProcDiscoverPlugin()
    diff_plugin = SimpleDiffPlugin()
    generate_plugin = MinimalSyzkallerGeneratePlugin()
    validate_plugin = SyzkallerBuildValidatePlugin()

    base_specs = discover_plugin.discover(ctx)
    discover_base = to_jsonable(base_specs)
    discover_base_v2 = adapt_discover_proc_v2(discover_base, ctx)

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
            discover_v2=discover_base_v2,
            ctx=ctx,
            client=llm_client,
            prompt_dir=prompt_dir,
            llm_enabled=llm_config.enabled,
            limit=_env_int("HM_AI_FUZZ_LLM_DISCOVER_LIMIT"),
        )

    discover_llm_v2 = _build_discover_llm_v2(discover_base_v2, discover_suggestions)
    discover_merged_v2 = _merge_discover_v2(discover_base_v2, discover_llm_v2)
    discover_llm = _discover_v2_to_json_specs(discover_llm_v2)
    merged_specs = _discover_v2_to_specs(discover_merged_v2)
    discover_merged = to_jsonable(merged_specs)

    diff_result = diff_plugin.diff(merged_specs, existing, ctx)
    diff_json = to_jsonable(diff_result)
    diff_v2 = adapt_diff_proc_v2(diff_json, discover_merged_v2)
    generation_v2_raw = generate_plugin.generate(diff_result, ctx)
    generate_json = to_jsonable(generation_v2_raw)
    generate_v2 = adapt_generate_proc_v2(generation_v2_raw, diff_v2)
    validation_result = validate_plugin.validate(generation_v2_raw, ctx)
    validate_json = to_jsonable(validation_result)
    validate_v2 = adapt_validate_proc_v2(validation_result)
    publish = _build_publish_summary(generation_v2_raw, validate_v2, ctx)

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
    result = {
        "discover": discover_base,
        "discover_llm": discover_llm,
        "discover_merged": discover_merged,
        "diff": diff_json,
        "generate": generate_json,
        "validate": validate_json,
        "discover_v2": discover_base_v2,
        "discover_llm_v2": discover_llm_v2,
        "discover_merged_v2": discover_merged_v2,
        "diff_v2": diff_v2,
        "generate_v2": generate_v2,
        "validate_v2": validate_v2,
        "publish": publish,
        "llm_discover_suggestions": discover_suggestions,
        "llm_model_suggestions": model_suggestions,
        "llm_fix_suggestions": fix_suggestions,
    }
    output_dir = args.out_dir.resolve()
    write_json(output_dir / "discover.json", discover_base)
    write_json(output_dir / "discover-llm.json", discover_llm)
    write_json(output_dir / "discover-merged.json", discover_merged)
    write_json(output_dir / "discover-v2.json", discover_base_v2)
    write_json(output_dir / "discover-llm-v2.json", discover_llm_v2)
    write_json(output_dir / "discover-merged-v2.json", discover_merged_v2)
    write_json(output_dir / "diff.json", diff_json)
    write_json(output_dir / "diff-v2.json", diff_v2)
    write_json(output_dir / "generate.json", generate_json)
    write_json(output_dir / "generate-v2.json", generate_v2)
    write_json(output_dir / "validate.json", validate_json)
    write_json(output_dir / "validate-v2.json", validate_v2)
    write_json(output_dir / "publish.json", publish)
    write_json(output_dir / "llm" / "discover-suggestions.json", discover_suggestions)
    write_json(output_dir / "llm" / "model-suggestions.json", model_suggestions)
    write_json(output_dir / "llm" / "fix-suggestions.json", fix_suggestions)
    write_json(args.out_json.resolve(), result)
    print(f"workflow result: {args.out_json.resolve()}")
    return 0


def _build_discover_llm_v2(discover_v2: dict[str, Any], discover_suggestions: dict[str, Any]) -> dict[str, Any]:
    base_by_id = {
        item["interface_id"]: item
        for item in discover_v2.get("items", [])
        if isinstance(item, dict) and isinstance(item.get("interface_id"), str)
    }
    llm_items: list[dict[str, Any]] = []
    suggestions = discover_suggestions.get("suggestions")
    if not isinstance(suggestions, list):
        suggestions = []
    for suggestion in suggestions:
        if not isinstance(suggestion, dict):
            continue
        interface_id = suggestion.get("interface_id")
        if not isinstance(interface_id, str):
            continue
        base_item = base_by_id.get(interface_id)
        if not isinstance(base_item, dict):
            continue
        suggested_ops = _normalize_llm_operations(suggestion.get("suggested_operations"))
        existing_ops = {
            str(op.get("op_name"))
            for op in base_item.get("operations", [])
            if isinstance(op, dict) and isinstance(op.get("op_name"), str)
        }
        new_ops = [op for op in suggested_ops if op not in existing_ops]
        if not new_ops:
            continue
        item = {
            **base_item,
            "operations": [_op_descriptor_from_name(interface_id, op) for op in new_ops],
            "analysis": {
                "confidence": suggestion.get("confidence", "medium"),
                "evidence": list(suggestion.get("evidence", [])) if isinstance(suggestion.get("evidence"), list) else [],
                "manual_todo": ["llm_discovered_operation"],
                "warnings": list(suggestion.get("warnings", [])) if isinstance(suggestion.get("warnings"), list) else [],
            },
            "llm_details": {
                "raw_suggested_operations": list(suggestion.get("suggested_operations", [])) if isinstance(suggestion.get("suggested_operations"), list) else [],
                "normalized_operations": new_ops,
            },
        }
        llm_items.append(item)
    return {
        "schema_version": "v2",
        "subsystem": "proc",
        "source_root": discover_v2.get("source_root", ""),
        "scope": dict(discover_v2.get("scope", {})),
        "items": llm_items,
        "summary": {
            "item_count": len(llm_items),
            "operation_count": sum(len(item.get("operations", [])) for item in llm_items),
        },
    }


def _merge_discover_v2(base_v2: dict[str, Any], llm_v2: dict[str, Any]) -> dict[str, Any]:
    merged_items: list[dict[str, Any]] = []
    llm_by_id = {
        item["interface_id"]: item
        for item in llm_v2.get("items", [])
        if isinstance(item, dict) and isinstance(item.get("interface_id"), str)
    }
    for base_item in base_v2.get("items", []):
        if not isinstance(base_item, dict):
            continue
        interface_id = base_item.get("interface_id")
        if not isinstance(interface_id, str):
            continue
        llm_item = llm_by_id.get(interface_id)
        base_ops = list(base_item.get("operations", [])) if isinstance(base_item.get("operations"), list) else []
        merged_ops = list(base_ops)
        seen = {
            str(op.get("op_name"))
            for op in merged_ops
            if isinstance(op, dict) and isinstance(op.get("op_name"), str)
        }
        llm_ops_added: list[str] = []
        if isinstance(llm_item, dict):
            for op in llm_item.get("operations", []):
                if not isinstance(op, dict):
                    continue
                op_name = op.get("op_name")
                if not isinstance(op_name, str) or op_name in seen:
                    continue
                seen.add(op_name)
                merged_ops.append(op)
                llm_ops_added.append(op_name)
        merged_analysis = dict(base_item.get("analysis", {})) if isinstance(base_item.get("analysis"), dict) else {}
        base_evidence = list(merged_analysis.get("evidence", [])) if isinstance(merged_analysis.get("evidence"), list) else []
        base_warnings = list(merged_analysis.get("warnings", [])) if isinstance(merged_analysis.get("warnings"), list) else []
        manual_todo = list(merged_analysis.get("manual_todo", [])) if isinstance(merged_analysis.get("manual_todo"), list) else []
        if isinstance(llm_item, dict):
            llm_analysis = llm_item.get("analysis", {})
            if isinstance(llm_analysis, dict):
                llm_evidence = llm_analysis.get("evidence", [])
                if isinstance(llm_evidence, list):
                    base_evidence.extend(str(item) for item in llm_evidence if isinstance(item, str))
                llm_warnings = llm_analysis.get("warnings", [])
                if isinstance(llm_warnings, list):
                    base_warnings.extend(str(item) for item in llm_warnings if isinstance(item, str))
            if llm_ops_added:
                manual_todo.append("merged_llm_operations")
        merged_item = {
            **base_item,
            "operations": merged_ops,
            "analysis": {
                **merged_analysis,
                "evidence": _unique_strings(base_evidence),
                "warnings": _unique_strings(base_warnings),
                "manual_todo": _unique_strings(manual_todo),
            },
            "merge_details": {
                "llm_operations_added": llm_ops_added,
                "sources": ["python"] + (["llm"] if llm_ops_added else []),
            },
        }
        merged_items.append(merged_item)
    return {
        "schema_version": "v2",
        "subsystem": "proc",
        "source_root": base_v2.get("source_root", ""),
        "scope": dict(base_v2.get("scope", {})),
        "items": merged_items,
        "summary": {
            "item_count": len(merged_items),
            "operation_count": sum(len(item.get("operations", [])) for item in merged_items),
        },
    }


def _discover_v2_to_specs(discover_v2: dict[str, Any]) -> list[InterfaceSpec]:
    specs: list[InterfaceSpec] = []
    for item in discover_v2.get("items", []):
        if not isinstance(item, dict):
            continue
        interface_id = item.get("interface_id")
        if not isinstance(interface_id, str):
            continue
        target = interface_id.split(":", 1)[1] if ":" in interface_id else interface_id
        operations = [
            str(op.get("op_name"))
            for op in item.get("operations", [])
            if isinstance(op, dict) and isinstance(op.get("op_name"), str)
        ]
        source = item.get("source", {}) if isinstance(item.get("source"), dict) else {}
        subsystem_details = item.get("subsystem_details", {}) if isinstance(item.get("subsystem_details"), dict) else {}
        analysis = item.get("analysis", {}) if isinstance(item.get("analysis"), dict) else {}
        specs.append(
            InterfaceSpec(
                subsystem=str(item.get("subsystem", "proc")),
                target=target,
                kind=str(item.get("interface_type", "misc")),
                capabilities=operations,
                source=SourceRef(
                    file=str(source.get("file", "")),
                    line=source.get("line") if isinstance(source.get("line"), int) else None,
                    symbol=str(source.get("symbol")) if isinstance(source.get("symbol"), str) else None,
                ),
                metadata={
                    "node_type": subsystem_details.get("node_type"),
                    "module_file": subsystem_details.get("module_file"),
                    "registration_kind": subsystem_details.get("registration_kind"),
                    "manual_todo": list(analysis.get("manual_todo", [])) if isinstance(analysis.get("manual_todo"), list) else [],
                },
            )
        )
    return specs


def _discover_v2_to_json_specs(discover_v2: dict[str, Any]) -> list[dict[str, Any]]:
    return to_jsonable(_discover_v2_to_specs(discover_v2))


def _normalize_llm_operations(value: object) -> list[str]:
    allowed = {"open", "read", "write", "lseek", "getdents64", "ioctl", "mmap", "poll"}
    synonyms = {
        "llseek": "lseek",
        "seek": "lseek",
        "readdir": "getdents64",
    }
    result: list[str] = []
    if not isinstance(value, list):
        return result
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = synonyms.get(item.strip().lower(), item.strip().lower())
        if normalized in allowed and normalized not in result:
            result.append(normalized)
    return result


def _op_descriptor_from_name(interface_id: str, op_name: str) -> dict[str, Any]:
    target = interface_id.split(":", 1)[1] if ":" in interface_id else interface_id
    from core.schema_adapter_v2 import _op_descriptor  # local import to avoid wider refactor

    return _op_descriptor("proc", target, op_name)


def _unique_strings(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result


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
