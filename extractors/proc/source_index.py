from __future__ import annotations

import os
import re
from pathlib import Path

from .models import OpsInfo, Registration
from .text_utils import (
    extract_balanced_call,
    find_enclosing_function,
    line_number,
    split_c_args,
    strip_comments,
    unquote_c_string,
)


PROC_CREATORS = {
    "proc_create",
    "proc_create_data",
    "proc_create_seq",
    "proc_create_seq_data",
    "proc_create_single",
    "proc_create_single_data",
    "proc_mkdir",
    "proc_mkdir_data",
    "proc_symlink",
}

SOURCE_SUFFIXES = {".c", ".h"}
SKIP_DIRS = {".git", "Documentation", "tools", "samples", "scripts"}
PRIMARY_SCAN_DIRS = ("fs/proc", "include/linux", "include/uapi", "kernel", "mm", "net")
SECONDARY_SCAN_DIRS = ("drivers", "security", "arch")
IGNORED_PROC_TERMS = {"proc", "sys", "self", "thread-self", "fs", "bus", "driver"}


class SourceIndex:
    def __init__(self, kernel_src: Path, scan_mode: str = "auto", proc_paths: list[str] | None = None):
        self.kernel_src = kernel_src.resolve()
        self.scan_mode = scan_mode
        self.proc_paths = proc_paths or []
        self.registrations: list[Registration] = []
        self.ops: dict[str, OpsInfo] = {}
        self.files: dict[str, str] = {}
        self.scanned_files = 0

    def build(self) -> "SourceIndex":
        for path in self._iter_source_files():
            rel = str(path.relative_to(self.kernel_src))
            try:
                source = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            clean = strip_comments(source)
            self.files[rel] = clean
            self.scanned_files += 1
            self.registrations.extend(self._parse_registrations(rel, clean))
            self.ops.update(self._parse_ops(rel, clean))
        return self

    def _iter_source_files(self):
        if self.scan_mode == "full":
            yield from self._iter_full_tree()
            return

        seen: set[Path] = set()
        terms = extract_proc_terms(self.proc_paths)
        for rel_dir in PRIMARY_SCAN_DIRS:
            root = self.kernel_src / rel_dir
            if not root.is_dir():
                continue
            for path in self._walk_dir(root):
                if path not in seen:
                    seen.add(path)
                    yield path
        for rel_dir in SECONDARY_SCAN_DIRS:
            root = self.kernel_src / rel_dir
            if not root.is_dir():
                continue
            for path in self._walk_dir(root, terms=terms):
                if path not in seen:
                    seen.add(path)
                    yield path

    def _iter_full_tree(self):
        for path in self.kernel_src.rglob("*"):
            if self._is_candidate_source(path):
                yield path

    def _walk_dir(self, root: Path, terms: set[str] | None = None):
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
            for filename in filenames:
                path = Path(dirpath) / filename
                if not self._is_candidate_source(path):
                    continue
                if terms and not file_matches_terms(path.relative_to(self.kernel_src), terms):
                    continue
                yield path

    def _is_candidate_source(self, path: Path) -> bool:
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            return False
        rel_parts = path.relative_to(self.kernel_src).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            return False
        return True

    def _parse_registrations(self, rel: str, source: str) -> list[Registration]:
        found: list[Registration] = []
        names = "|".join(re.escape(name) for name in sorted(PROC_CREATORS, key=len, reverse=True))
        pattern = re.compile(rf"\b({names})\s*\(")
        for match in pattern.finditer(source):
            call = extract_balanced_call(source, match.start())
            if not call:
                continue
            raw_call, _ = call
            args_text = raw_call[raw_call.find("(") + 1 : -1]
            args = split_c_args(args_text)
            kind = match.group(1)
            found.append(
                Registration(
                    kind=kind,
                    name=unquote_c_string(args[0]) if args else None,
                    parent=self._parent_arg(kind, args),
                    ops_symbol=self._ops_arg(kind, args),
                    file=rel,
                    function=find_enclosing_function(source, match.start()),
                    line=line_number(source, match.start()),
                    raw_call=" ".join(raw_call.split()),
                    assigned_symbol=self._assigned_symbol(source, match.start()),
                )
            )
        return found

    def _parse_ops(self, rel: str, source: str) -> dict[str, OpsInfo]:
        out: dict[str, OpsInfo] = {}
        pattern = re.compile(
            r"(?:static\s+)?(?:const\s+)?struct\s+(proc_ops|file_operations)\s+"
            r"([A-Za-z_]\w*)\s*=\s*\{(?P<body>.*?)\};",
            re.S,
        )
        for match in pattern.finditer(source):
            kind, symbol = match.group(1), match.group(2)
            body = match.group("body")
            callbacks = {
                field: _clean_symbol(value)
                for field, value in re.findall(r"\.([A-Za-z_]\w*)\s*=\s*([^,\n}]+)", body)
            }
            compat_handlers = [callbacks["compat_ioctl"]] if "compat_ioctl" in callbacks else []
            is_seq = any("seq_" in value or value in {"single_open", "seq_read"} for value in callbacks.values())
            out[symbol] = OpsInfo(
                symbol=symbol,
                kind=kind,
                file=rel,
                line=line_number(source, match.start()),
                callbacks=callbacks,
                supported_ops=callbacks_to_supported_ops(callbacks),
                compat_ioctl_handlers=compat_handlers,
                is_seq_file=is_seq,
            )
        return out

    @staticmethod
    def _parent_arg(kind: str, args: list[str]) -> str | None:
        if kind == "proc_symlink":
            return args[1].strip() if len(args) > 1 else None
        if kind.startswith("proc_mkdir"):
            return args[1].strip() if len(args) > 1 else None
        return args[2].strip() if len(args) > 2 else None

    @staticmethod
    def _ops_arg(kind: str, args: list[str]) -> str | None:
        if kind in {"proc_mkdir", "proc_mkdir_data", "proc_symlink"}:
            return None
        if kind in {"proc_create", "proc_create_data", "proc_create_seq", "proc_create_seq_data"}:
            return _clean_symbol(args[3]) if len(args) > 3 else None
        return None

    @staticmethod
    def _assigned_symbol(source: str, offset: int) -> str | None:
        line_start = source.rfind("\n", 0, offset) + 1
        prefix = source[line_start:offset]
        match = re.search(r"([A-Za-z_]\w*)\s*=\s*$", prefix)
        return match.group(1) if match else None


def callbacks_to_supported_ops(callbacks: dict[str, str]) -> list[str]:
    mapping = {
        "proc_open": "open",
        "open": "open",
        "proc_read": "read",
        "read": "read",
        "read_iter": "read",
        "proc_write": "write",
        "write": "write",
        "write_iter": "write",
        "proc_lseek": "lseek",
        "llseek": "lseek",
        "proc_poll": "poll",
        "poll": "poll",
        "proc_ioctl": "ioctl",
        "unlocked_ioctl": "ioctl",
        "proc_mmap": "mmap",
        "mmap": "mmap",
        "splice_read": "splice",
    }
    ordered: list[str] = []
    for field in callbacks:
        op = mapping.get(field)
        if op and op not in ordered:
            ordered.append(op)
    if "open" not in ordered:
        ordered.insert(0, "open")
    if any(value in {"seq_read", "single_open"} or "seq_" in value for value in callbacks.values()):
        for op in ("read", "lseek"):
            if op not in ordered:
                ordered.append(op)
    return ordered


def _clean_symbol(value: str) -> str:
    value = value.strip()
    value = value.lstrip("&")
    return re.sub(r"\s+", " ", value)


def extract_proc_terms(proc_paths: list[str]) -> set[str]:
    terms: set[str] = set()
    for proc_path in proc_paths:
        for part in proc_path.strip("/").split("/"):
            part = part.strip().lower()
            if not part or part in IGNORED_PROC_TERMS:
                continue
            if part.startswith("<") and part.endswith(">"):
                continue
            if part.startswith("{") and part.endswith("}"):
                continue
            if len(part) < 3 and part not in {"ip", "vm"}:
                continue
            terms.add(part)
            if "_" in part:
                terms.update(token for token in part.split("_") if len(token) >= 3)
            if "-" in part:
                terms.update(token for token in part.split("-") if len(token) >= 3)
    return terms


def file_matches_terms(rel_path: Path, terms: set[str]) -> bool:
    if not terms:
        return True
    haystack = "/".join(rel_path.parts).lower()
    stem = rel_path.stem.lower()
    if "proc" in haystack or "sysctl" in haystack:
        return True
    return any(term in haystack or term in stem for term in terms)
