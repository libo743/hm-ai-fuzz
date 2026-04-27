from __future__ import annotations

from typing import Any

from .protocols import WorkflowContext
from .schemas import DiffResult, GeneratedFile, GenerationResult, ValidationResult

_OP_TO_BINDING: dict[str, dict[str, Any]] = {
    "open": {
        "syscall_name": "openat",
        "syscall_family": "fs_path",
        "syscall_nr_symbol": "__NR_openat",
        "call_form": "openat",
        "arguments": [
            {"name": "dirfd", "arg_role": "dirfd", "type_hint": "fd_dir"},
            {"name": "file", "arg_role": "path", "type_hint": "string"},
            {"name": "flags", "arg_role": "flags", "type_hint": "open_flags"},
            {"name": "mode", "arg_role": "mode", "type_hint": "open_mode"},
        ],
    },
    "read": {
        "syscall_name": "read",
        "syscall_family": "fs_io",
        "syscall_nr_symbol": "__NR_read",
        "call_form": "read",
        "arguments": [
            {"name": "fd", "arg_role": "fd", "type_hint": "fd"},
            {"name": "buf", "arg_role": "buffer", "type_hint": "buffer[out]"},
            {"name": "count", "arg_role": "length", "type_hint": "len"},
        ],
    },
    "write": {
        "syscall_name": "write",
        "syscall_family": "fs_io",
        "syscall_nr_symbol": "__NR_write",
        "call_form": "write",
        "arguments": [
            {"name": "fd", "arg_role": "fd", "type_hint": "fd"},
            {"name": "buf", "arg_role": "buffer", "type_hint": "buffer[in]"},
            {"name": "count", "arg_role": "length", "type_hint": "len"},
        ],
    },
    "lseek": {
        "syscall_name": "lseek",
        "syscall_family": "fs_io",
        "syscall_nr_symbol": "__NR_lseek",
        "call_form": "lseek",
        "arguments": [
            {"name": "fd", "arg_role": "fd", "type_hint": "fd"},
            {"name": "offset", "arg_role": "offset", "type_hint": "fileoff"},
            {"name": "whence", "arg_role": "flags", "type_hint": "seek_whence"},
        ],
    },
    "getdents64": {
        "syscall_name": "getdents64",
        "syscall_family": "fs_io",
        "syscall_nr_symbol": "__NR_getdents64",
        "call_form": "getdents64",
        "arguments": [
            {"name": "fd", "arg_role": "fd", "type_hint": "fd_dir"},
            {"name": "dirent", "arg_role": "buffer", "type_hint": "buffer[out]"},
            {"name": "count", "arg_role": "length", "type_hint": "len"},
        ],
    },
    "ioctl": {
        "syscall_name": "ioctl",
        "syscall_family": "fs_ioctl",
        "syscall_nr_symbol": "__NR_ioctl",
        "call_form": "ioctl",
        "arguments": [
            {"name": "fd", "arg_role": "fd", "type_hint": "fd"},
            {"name": "cmd", "arg_role": "command", "type_hint": "int32"},
            {"name": "arg", "arg_role": "buffer", "type_hint": "buffer[in]"},
        ],
    },
    "mmap": {
        "syscall_name": "mmap",
        "syscall_family": "fs_mmap",
        "syscall_nr_symbol": "__NR_mmap",
        "call_form": "mmap",
        "arguments": [
            {"name": "addr", "arg_role": "addr", "type_hint": "vma"},
            {"name": "len", "arg_role": "length", "type_hint": "len"},
            {"name": "prot", "arg_role": "flags", "type_hint": "mmap_prot"},
            {"name": "flags", "arg_role": "flags", "type_hint": "mmap_flags"},
            {"name": "fd", "arg_role": "fd", "type_hint": "fd"},
            {"name": "offset", "arg_role": "offset", "type_hint": "intptr"},
        ],
    },
    "poll": {
        "syscall_name": "poll",
        "syscall_family": "fs_poll",
        "syscall_nr_symbol": "__NR_poll",
        "call_form": "poll",
        "arguments": [
            {"name": "ufds", "arg_role": "fd_array", "type_hint": "pollfd[]"},
            {"name": "nfds", "arg_role": "length", "type_hint": "int"},
            {"name": "timeout", "arg_role": "timeout", "type_hint": "int32"},
        ],
    },
}

_OP_TO_TYPE = {
    "open": "path_open",
    "read": "fd_io",
    "write": "fd_io",
    "lseek": "fd_io",
    "getdents64": "dir_iter",
    "ioctl": "fd_ioctl",
    "mmap": "fd_mmap",
    "poll": "fd_poll",
}


def adapt_discover_proc_v2(discover: list[dict[str, Any]], ctx: WorkflowContext) -> dict[str, Any]:
    items = [_discover_item_to_v2(item) for item in discover]
    return {
        "schema_version": "v2",
        "subsystem": "proc",
        "source_root": str(ctx.kernel_src) if ctx.kernel_src is not None else "",
        "scope": {
            "module": str(ctx.config.get("target_module", "fs/proc")),
            "search_method": str(ctx.config.get("search_method", "prefix")),
            "scan_mode": str(ctx.config.get("scan_mode", "auto")),
        },
        "items": items,
        "summary": {
            "item_count": len(items),
            "warning_count": sum(len(item.get("analysis", {}).get("warnings", [])) for item in items),
        },
    }


def adapt_diff_proc_v2(diff: dict[str, Any], discover_v2: dict[str, Any]) -> dict[str, Any]:
    discover_by_id = {item["interface_id"]: item for item in discover_v2.get("items", [])}
    new_items = [_diff_item_to_v2(item, discover_by_id) for item in diff.get("new_items", [])]
    current_count = sum(len(item.get("operations", [])) for item in discover_v2.get("items", []))
    return {
        "schema_version": "v2",
        "subsystem": "proc",
        "new_items": new_items,
        "summary": {
            "current_count": current_count,
            "baseline_count": len(diff.get("existing_keys", [])),
            "new_count": len(new_items),
        },
    }


def diff_v2_to_diff_result(diff_v2: dict[str, Any]) -> DiffResult:
    new_items: list[dict[str, Any]] = []
    for item in diff_v2.get("new_items", []):
        if not isinstance(item, dict):
            continue
        target = _target_from_interface_id(str(item.get("interface_id", "")))
        op = str(item.get("operation", {}).get("op_name", ""))
        node_type = str(item.get("subsystem_details", {}).get("node_type", "file"))
        source = item.get("source", {}) if isinstance(item.get("source"), dict) else {}
        subsystem_details = item.get("subsystem_details", {}) if isinstance(item.get("subsystem_details"), dict) else {}
        new_items.append(
            {
                "subsystem": item.get("subsystem", "proc") if isinstance(item.get("subsystem"), str) else "proc",
                "target": target,
                "op": op,
                "node_type": node_type,
                "module_file": subsystem_details.get("module_file"),
                "impl_file": source.get("file"),
                "impl_line": source.get("line"),
                "symbol": source.get("symbol"),
                "registration_kind": subsystem_details.get("registration_kind"),
                "suggested_case_file": subsystem_details.get("suggested_case_file"),
            }
        )
    return DiffResult(new_items=new_items)


def adapt_generate_proc_v2(generation: GenerationResult, diff_v2: dict[str, Any]) -> dict[str, Any]:
    generated_files = [
        {
            "path": item.path,
            "kind": item.kind,
            "details": dict(item.details),
        }
        for item in generation.generated_files
    ]
    item_to_unit = _build_item_to_unit_map(generation.units)
    generated_units: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []
    for item in diff_v2.get("new_items", []):
        if not isinstance(item, dict):
            continue
        item_key = str(item.get("item_key", ""))
        symbol_name = item_to_unit.get(item_key)
        if symbol_name is None:
            skipped_items.append(
                {
                    "item_key": item_key,
                    "reason": "unsupported_or_not_emitted",
                    "details": {
                        "operation": item.get("operation", {}).get("op_name"),
                        "interface_id": item.get("interface_id"),
                    },
                }
            )
            continue
        generated_units.append(
            {
                "item_key": item_key,
                "unit_kind": "syz_alias",
                "symbol_name": symbol_name,
                "source_file": generated_files[0]["path"] if generated_files else "",
                "details": {
                    "operation": item.get("operation", {}).get("op_name"),
                    "interface_id": item.get("interface_id"),
                },
            }
        )
    return {
        "schema_version": "v2",
        "subsystem": "proc",
        "generated_files": generated_files,
        "generated_units": generated_units,
        "skipped_items": skipped_items,
        "summary": {
            "generated_count": len(generated_units),
            "skipped_count": len(skipped_items),
        },
    }


def generate_v2_to_generation_result(generate_v2: dict[str, Any]) -> GenerationResult:
    return GenerationResult(
        generated_files=[
            GeneratedFile(path=str(item["path"]), kind=str(item["kind"]), details=dict(item.get("details", {})))
            for item in generate_v2.get("generated_files", [])
            if isinstance(item, dict)
        ],
        units=list(generate_v2.get("generated_units", [])),
        metadata={
            "schema_version": generate_v2.get("schema_version", "v2"),
            "summary": dict(generate_v2.get("summary", {})),
        },
    )


def adapt_validate_proc_v2(validation: ValidationResult) -> dict[str, Any]:
    metadata = dict(validation.metadata)
    return {
        "schema_version": "v2",
        "subsystem": "proc",
        "status": validation.status,
        "diagnostics": list(validation.diagnostics),
        "summary": {
            "returncode": metadata.get("returncode"),
            "duration_sec": metadata.get("duration_sec"),
        },
        "metadata": metadata,
    }


def _discover_item_to_v2(item: dict[str, Any]) -> dict[str, Any]:
    target = str(item["target"])
    interface_type = _interface_type_from_kind(str(item.get("kind", "misc")))
    ops = [_op_descriptor("proc", target, op) for op in item.get("capabilities", []) if isinstance(op, str)]
    metadata = dict(item.get("metadata", {}))
    source = dict(item.get("source", {})) if isinstance(item.get("source"), dict) else {}
    return {
        "interface_id": f"proc:{target}",
        "interface_type": interface_type,
        "subsystem": "proc",
        "display_name": target,
        "access_paths": [target],
        "operations": ops,
        "source": {
            "file": source.get("file", metadata.get("module_file", "")),
            "line": source.get("line"),
            "symbol": source.get("symbol"),
            "symbol_kind": "proc_ops" if source.get("symbol") else None,
            "source_kind": metadata.get("registration_kind"),
            "related_symbols": [source["symbol"]] if isinstance(source.get("symbol"), str) else [],
        },
        "attributes": {
            "resource_kind": "fd",
            "object_kind": "kernel_interface",
            "is_virtual": True,
            "is_path_based": True,
            "is_fd_based": True,
            "is_stateful": False,
        },
        "subsystem_details": {
            "node_type": metadata.get("node_type"),
            "registration_kind": metadata.get("registration_kind"),
            "module_file": metadata.get("module_file"),
            "ops_symbol": source.get("symbol"),
            "parent_path": _parent_path(target),
        },
        "analysis": {
            "confidence": _confidence_from_metadata(metadata),
            "evidence": _evidence_from_item(target, ops, metadata, source),
            "manual_todo": list(metadata.get("manual_todo", [])) if isinstance(metadata.get("manual_todo"), list) else [],
            "warnings": list(metadata.get("manual_todo", [])) if isinstance(metadata.get("manual_todo"), list) else [],
        },
    }


def _diff_item_to_v2(item: dict[str, Any], discover_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    target = str(item["target"])
    op = str(item["op"])
    interface_id = f"proc:{target}"
    discover_item = discover_by_id.get(interface_id, {})
    operation = _op_descriptor("proc", target, op)
    return {
        "item_key": f"{interface_id}#{op}",
        "interface_id": interface_id,
        "subsystem": "proc",
        "interface_type": discover_item.get("interface_type", _interface_type_from_kind(str(item.get("node_type", "misc")))),
        "operation": {
            "op_name": operation["op_name"],
            "op_type": operation["op_type"],
            "direction": operation.get("direction"),
        },
        "syscall_bindings": operation.get("syscall_bindings", []),
        "access_paths": discover_item.get("access_paths", [target]),
        "source": {
            "file": item.get("impl_file") or item.get("module_file") or "",
            "line": item.get("impl_line"),
            "symbol": item.get("symbol"),
            "symbol_kind": "proc_ops" if item.get("symbol") else None,
            "source_kind": item.get("registration_kind"),
            "related_symbols": [item["symbol"]] if isinstance(item.get("symbol"), str) else [],
        },
        "attributes": discover_item.get("attributes", {}),
        "subsystem_details": {
            **discover_item.get("subsystem_details", {}),
            "node_type": item.get("node_type"),
            "registration_kind": item.get("registration_kind"),
            "module_file": item.get("module_file"),
            "suggested_case_file": item.get("suggested_case_file"),
        },
        "analysis": discover_item.get("analysis", {"confidence": "medium", "evidence": [], "manual_todo": [], "warnings": []}),
    }


def _op_descriptor(subsystem: str, target: str, op: str) -> dict[str, Any]:
    binding = dict(_OP_TO_BINDING.get(op, {
        "syscall_name": op,
        "syscall_family": "custom",
        "syscall_nr_symbol": None,
        "call_form": op,
        "arguments": [],
    }))
    return {
        "op_id": f"{subsystem}:{target}#{op}",
        "op_name": op,
        "op_type": _OP_TO_TYPE.get(op, "custom"),
        "direction": _direction_from_op(op),
        "requirements": _requirements_from_op(op),
        "syscall_bindings": [binding],
        "generation_hints": {
            "target_style": "syzkaller_alias",
        },
        "analysis": {
            "confidence": "high" if op in _OP_TO_BINDING else "medium",
            "evidence": [f"mapped operation {op} to syscall binding {binding['syscall_name']}"],
            "manual_todo": [],
            "warnings": [],
        },
    }


def _interface_type_from_kind(kind: str) -> str:
    mapping = {
        "virtual_file": "file_like",
        "virtual_dir": "dir_like",
        "virtual_symlink": "symlink_like",
        "dynamic_virtual_path": "virtual_interface",
    }
    return mapping.get(kind, "misc")


def _direction_from_op(op: str) -> str:
    if op in {"read", "getdents64"}:
        return "out"
    if op in {"write", "ioctl"}:
        return "in"
    if op in {"poll"}:
        return "inout"
    return "none"


def _requirements_from_op(op: str) -> dict[str, bool]:
    return {
        "needs_fd": op != "open",
        "needs_path": op == "open",
        "needs_socket": False,
        "needs_struct": op in {"ioctl", "poll"},
        "needs_resource": op in {"open", "read", "write", "lseek", "getdents64", "ioctl", "mmap", "poll"},
    }


def _confidence_from_metadata(metadata: dict[str, Any]) -> str:
    todos = metadata.get("manual_todo")
    if isinstance(todos, list) and todos:
        return "medium"
    return "high"


def _evidence_from_item(target: str, ops: list[dict[str, Any]], metadata: dict[str, Any], source: dict[str, Any]) -> list[str]:
    evidence = [f"discovered proc target {target}", f"resolved {len(ops)} operations"]
    if metadata.get("registration_kind"):
        evidence.append(f"registration kind: {metadata['registration_kind']}")
    if source.get("symbol"):
        evidence.append(f"resolved ops symbol: {source['symbol']}")
    return evidence


def _parent_path(target: str) -> str:
    if "/" not in target.strip("/"):
        return "/"
    parent = "/" + "/".join(target.strip("/").split("/")[:-1])
    return parent or "/"


def _target_from_interface_id(interface_id: str) -> str:
    if ":" not in interface_id:
        return interface_id
    _, target = interface_id.split(":", 1)
    return target


def _build_item_to_unit_map(units: list[dict[str, Any]]) -> dict[str, str]:
    item_to_unit: dict[str, str] = {}
    for unit in units:
        target = unit.get("target")
        supported_ops = unit.get("supported_ops")
        if not isinstance(target, str) or not isinstance(supported_ops, list):
            continue
        safe = target.strip("/").replace("/", "_")
        for op in supported_ops:
            if not isinstance(op, str):
                continue
            symbol_name = _symbol_name_for_proc_op(safe, op)
            if symbol_name is None:
                continue
            item_to_unit[f"proc:{target}#{op}"] = symbol_name
    return item_to_unit


def _symbol_name_for_proc_op(safe: str, op: str) -> str | None:
    if op == "open":
        return f"openat$proc_{safe}"
    if op == "read":
        return f"read$proc_{safe}"
    if op == "write":
        return f"write$proc_{safe}"
    if op == "lseek":
        return f"lseek$proc_{safe}"
    if op == "ioctl":
        return f"ioctl$proc_{safe}"
    if op == "mmap":
        return f"mmap$proc_{safe}"
    if op == "poll":
        return f"poll$proc_{safe}"
    if op == "getdents64":
        return "getdents64"
    return None
