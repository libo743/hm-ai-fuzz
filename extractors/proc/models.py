from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Registration:
    kind: str
    name: str | None
    parent: str | None
    ops_symbol: str | None
    file: str
    function: str | None
    line: int
    raw_call: str
    assigned_symbol: str | None = None
    resolved_path: str | None = None


@dataclass
class OpsInfo:
    symbol: str
    kind: str
    file: str
    line: int
    callbacks: dict[str, str] = field(default_factory=dict)
    supported_ops: list[str] = field(default_factory=list)
    compat_ioctl_handlers: list[str] = field(default_factory=list)
    is_seq_file: bool = False


@dataclass
class ProcNodeMatch:
    proc_path: str
    node_type: str = "unknown"
    ops_symbol: str | None = None
    supported_ops: list[str] = field(default_factory=list)
    impl_file: str | None = None
    impl_line: int | None = None
    module_file: str | None = None
    registration_kind: str | None = None
    manual_todo: list[str] = field(default_factory=list)
