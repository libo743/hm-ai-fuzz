from __future__ import annotations

import re

from core.protocols import WorkflowContext
from core.schemas import DiffResult, InterfaceSpec


class SimpleDiffPlugin:
    name = "simple-diff"

    def diff(self, current: list[InterfaceSpec], existing: object, ctx: WorkflowContext) -> DiffResult:
        current_items = _flatten_interface_items(current)
        existing_keys = _extract_existing_keys(existing)
        new_items = [item for item in current_items if _interface_item_key(item) not in existing_keys]
        new_specs = [_item_to_spec(item) for item in new_items]
        return DiffResult(
            current=current,
            existing_keys=sorted(existing_keys),
            new=new_specs,
            new_items=new_items,
        )


def _interface_key(spec: InterfaceSpec) -> str:
    caps = ",".join(sorted(spec.capabilities))
    return f"{spec.subsystem}:{spec.target}:{caps}"


def _interface_item_key(item: dict[str, object]) -> str:
    return f"{item['subsystem']}:{item['target']}:{item['op']}"


def _flatten_interface_items(current: list[InterfaceSpec]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for spec in current:
        node_type = str(spec.metadata.get("node_type", spec.kind))
        module_file = spec.metadata.get("module_file")
        registration_kind = spec.metadata.get("registration_kind")
        for op in spec.capabilities:
            items.append(
                {
                    "subsystem": spec.subsystem,
                    "target": spec.target,
                    "op": op,
                    "node_type": node_type,
                    "module_file": module_file,
                    "impl_file": spec.source.file if spec.source else None,
                    "impl_line": spec.source.line if spec.source else None,
                    "symbol": spec.source.symbol if spec.source else None,
                    "registration_kind": registration_kind,
                    "suggested_case_file": _suggested_case_file(spec.target, op),
                }
            )
    return items


def _item_to_spec(item: dict[str, object]) -> InterfaceSpec:
    return InterfaceSpec(
        subsystem=str(item["subsystem"]),
        target=str(item["target"]),
        kind=str(item["node_type"]),
        capabilities=[str(item["op"])],
        metadata={k: v for k, v in item.items() if k not in {"subsystem", "target", "node_type", "op"}},
    )


def _extract_existing_keys(existing: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(existing, dict):
        interfaces = existing.get("interfaces")
        if isinstance(interfaces, list):
            for item in interfaces:
                key = _parse_existing_item(item)
                if key:
                    keys.add(key)
        new_interfaces = existing.get("new_interfaces")
        if isinstance(new_interfaces, list):
            for item in new_interfaces:
                key = _parse_existing_item(item)
                if key:
                    keys.add(key)
        discover = existing.get("discover")
        if isinstance(discover, list):
            for item in discover:
                if not isinstance(item, dict):
                    continue
                subsystem = item.get("subsystem")
                target = item.get("target")
                caps = item.get("capabilities")
                if isinstance(subsystem, str) and isinstance(target, str) and isinstance(caps, list):
                    for op in caps:
                        if isinstance(op, str):
                            keys.add(f"{subsystem}:{target}:{op}")
    elif isinstance(existing, list):
        for item in existing:
            if isinstance(item, str):
                keys.add(item)
            else:
                key = _parse_existing_item(item)
                if key:
                    keys.add(key)
    return keys


def _parse_existing_item(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    subsystem = item.get("subsystem", "proc")
    target = item.get("target") or item.get("proc_path")
    op = item.get("op") or item.get("syscall")
    if isinstance(subsystem, str) and isinstance(target, str) and isinstance(op, str):
        return f"{subsystem}:{target}:{op}"
    return None


def _suggested_case_file(target: str, op: str) -> str:
    safe_target = re.sub(r"[^A-Za-z0-9_.-]+", "_", target.strip("/")) or "target"
    safe_op = re.sub(r"[^A-Za-z0-9_.-]+", "_", op) or "op"
    return f"{safe_target}__{safe_op}.json"
