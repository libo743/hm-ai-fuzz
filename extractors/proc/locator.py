from __future__ import annotations

from .models import ProcNodeMatch, Registration
from .proc_paths import is_dynamic_proc_path
from .source_index import SourceIndex


ROOT_PARENTS = {"NULL", "0", "proc_root", "proc_root_fs", "proc_root_kcore"}
KNOWN_PARENT_PATHS = {"proc_net": "/proc/net", "init_net.proc_net": "/proc/net"}


class ProcLocator:
    def __init__(self, index: SourceIndex):
        self.index = index
        self.by_assigned_symbol = {
            reg.assigned_symbol: reg for reg in index.registrations if reg.assigned_symbol and reg.name
        }

    def locate(self, proc_path: str) -> ProcNodeMatch:
        node = ProcNodeMatch(proc_path=proc_path)
        if is_dynamic_proc_path(proc_path):
            node.manual_todo.append("dynamic proc path; static registration may require pattern-specific rules")

        exact = [reg for reg in self.index.registrations if reg.resolved_path == proc_path]
        suffix = [] if exact else self._suffix_candidates(proc_path)
        candidates = exact or suffix
        if not candidates:
            node.manual_todo.append("no matching proc registration found in source index")
            return node

        best = candidates[0]
        node.node_type = self._node_type(best)
        node.ops_symbol = best.ops_symbol
        node.impl_file = best.file
        node.impl_line = best.line
        node.module_file = best.file
        node.registration_kind = best.kind
        if len(candidates) > 1:
            node.manual_todo.append(f"{len(candidates)} candidate implementations found; review confidence scores")
        return node

    def resolve_registration_paths(self) -> None:
        for reg in self.index.registrations:
            reg.resolved_path = self._resolve_path(reg, seen=set())

    def _resolve_path(self, reg: Registration, seen: set[str]) -> str | None:
        if not reg.name:
            return None
        parent_path = self._resolve_parent(reg.parent, seen)
        if parent_path is None:
            return None
        return f"{parent_path.rstrip('/')}/{reg.name}".replace("//", "/")

    def _resolve_parent(self, parent: str | None, seen: set[str]) -> str | None:
        if parent is None or parent in ROOT_PARENTS:
            return "/proc"
        if parent in KNOWN_PARENT_PATHS:
            return KNOWN_PARENT_PATHS[parent]
        parent = parent.strip("&")
        if parent in self.by_assigned_symbol:
            if parent in seen:
                return None
            seen.add(parent)
            return self._resolve_path(self.by_assigned_symbol[parent], seen)
        if parent.startswith('"') and parent.endswith('"'):
            return "/proc/" + parent.strip('"').strip("/")
        return None

    def _suffix_candidates(self, proc_path: str) -> list[Registration]:
        basename = proc_path.rsplit("/", 1)[-1]
        candidates = [reg for reg in self.index.registrations if reg.name == basename]
        return sorted(
            candidates,
            key=lambda reg: (
                0 if reg.resolved_path and proc_path.endswith(reg.resolved_path.removeprefix("/proc")) else 1,
                reg.file,
                reg.line,
            ),
        )

    @staticmethod
    def _node_type(reg: Registration) -> str:
        if reg.kind.startswith("proc_mkdir"):
            return "dir"
        if reg.kind == "proc_symlink":
            return "symlink"
        return "file"
