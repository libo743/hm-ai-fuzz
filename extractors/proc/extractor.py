from __future__ import annotations

from core.protocols import WorkflowContext
from core.schemas import InterfaceSpec, SourceRef

from .locator import ProcLocator
from .ops import OpsResolver
from .source_index import SKIP_DIRS, SOURCE_SUFFIXES, SourceIndex
from .text_utils import strip_comments
import os
from pathlib import Path


class ProcDiscoverPlugin:
    name = "proc"

    def discover(self, ctx: WorkflowContext) -> list[InterfaceSpec]:
        if ctx.kernel_src is None:
            raise ValueError("kernel_src is required for proc discovery")
        target_subsystem = str(ctx.config.get("target_subsystem", "proc"))
        scope_path = _normalize_optional_scope_path(
            ctx.config.get("scope_path", ctx.config.get("target_module", "fs/proc"))
        )
        search_method = str(ctx.config.get("search_method", "prefix"))
        scan_mode = str(ctx.config.get("scan_mode", "auto"))
        scope_strategy = str(ctx.config.get("scope_strategy", "hybrid"))
        semantic_signals = _normalize_semantic_signals(ctx.config.get("semantic_signals", []))

        index = _build_target_index(
            kernel_src=ctx.kernel_src,
            scope_path=scope_path,
            search_method=search_method,
            scan_mode=scan_mode,
        )
        locator = ProcLocator(index)
        locator.resolve_registration_paths()
        ops = OpsResolver(index)

        matched_regs = [reg for reg in index.registrations if reg.resolved_path]
        if scope_path is not None:
            matched_regs = [
                reg
                for reg in matched_regs
                if _matches_module(reg.file, scope_path, search_method)
            ]

        specs: list[InterfaceSpec] = []
        seen: set[str] = set()
        for reg in matched_regs:
            proc_path = reg.resolved_path
            if proc_path is None or proc_path in seen:
                continue
            seen.add(proc_path)
            node = locator.locate(proc_path)
            ops.enrich(node)
            specs.append(
                InterfaceSpec(
                    subsystem="proc",
                    target=node.proc_path,
                    kind=_spec_kind(node.node_type),
                    capabilities=node.supported_ops,
                    source=SourceRef(
                        file=node.impl_file or reg.file,
                        line=node.impl_line,
                        symbol=node.ops_symbol,
                    ),
                    metadata={
                        "target_subsystem": target_subsystem,
                        "scope_path": scope_path,
                        "search_method": search_method,
                        "scan_mode": scan_mode,
                        "scope_strategy": scope_strategy,
                        "semantic_signals": semantic_signals,
                        "node_type": node.node_type,
                        "module_file": node.module_file or reg.file,
                        "registration_kind": node.registration_kind or reg.kind,
                        "manual_todo": node.manual_todo,
                        "files_scanned": index.scanned_files,
                        "registrations_scanned": len(index.registrations),
                    },
                )
            )
        return specs


def _matches_module(source_file: str, target_module: str, search_method: str) -> bool:
    candidate = source_file.strip("/")
    if search_method == "exact":
        return candidate == target_module
    if search_method == "prefix":
        return candidate.startswith(target_module.rstrip("/") + "/") or candidate == target_module
    return target_module in candidate


def _spec_kind(node_type: str) -> str:
    mapping = {
        "file": "virtual_file",
        "dir": "virtual_dir",
        "symlink": "virtual_symlink",
        "dynamic": "dynamic_virtual_path",
        "unknown": "unknown",
    }
    return mapping.get(node_type, node_type)


def _normalize_optional_scope_path(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().strip("/")
    return text or None


def _normalize_semantic_signals(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _build_target_index(*, kernel_src: Path, scope_path: str | None, search_method: str, scan_mode: str) -> SourceIndex:
    if scope_path is None:
        return SourceIndex(kernel_src, scan_mode=scan_mode).build()
    module_root = kernel_src / scope_path
    if search_method in {"exact", "prefix"} and module_root.exists():
        narrow = SourceIndex(kernel_src, scan_mode=scan_mode)
        for path in _iter_target_files(module_root):
            rel = str(path.relative_to(kernel_src))
            try:
                source = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            clean = strip_comments(source)
            narrow.files[rel] = clean
            narrow.scanned_files += 1
            narrow.registrations.extend(narrow._parse_registrations(rel, clean))
            narrow.ops.update(narrow._parse_ops(rel, clean))
        return narrow
    return SourceIndex(kernel_src, scan_mode=scan_mode).build()


def _iter_target_files(root: Path):
    if root.is_file():
        if root.suffix in SOURCE_SUFFIXES:
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix in SOURCE_SUFFIXES and path.is_file():
                yield path
