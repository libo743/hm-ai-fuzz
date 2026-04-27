from __future__ import annotations


def is_dynamic_proc_path(path: str) -> bool:
    dynamic_markers = ("<pid>", "<tid>", "{pid}", "{tid}")
    return any(marker in path for marker in dynamic_markers)
