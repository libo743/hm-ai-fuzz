from __future__ import annotations

from .models import ProcNodeMatch
from .source_index import SourceIndex


class OpsResolver:
    def __init__(self, index: SourceIndex):
        self.index = index

    def enrich(self, node: ProcNodeMatch) -> None:
        if node.node_type == "dir":
            node.supported_ops = ["open", "getdents64"]
            return
        if not node.ops_symbol:
            self._fallback(node)
            return
        ops = self.index.ops.get(node.ops_symbol)
        if not ops:
            node.manual_todo.append(f"ops symbol {node.ops_symbol} was not resolved")
            self._fallback(node)
            return
        node.supported_ops = list(ops.supported_ops)
        if ops.is_seq_file:
            for op in ("read", "lseek"):
                if op not in node.supported_ops:
                    node.supported_ops.append(op)
        if ops.compat_ioctl_handlers:
            node.manual_todo.append(
                "compat_ioctl handler found; current discovery records it but generation is not modeled yet"
            )

    @staticmethod
    def _fallback(node: ProcNodeMatch) -> None:
        if not node.supported_ops:
            node.supported_ops = ["open", "read"]
            node.manual_todo.append("using conservative open/read fallback because ops could not be resolved")
