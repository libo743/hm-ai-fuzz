from __future__ import annotations

import re


def strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), source, flags=re.S)
    source = re.sub(r"//.*", "", source)
    return source


def split_c_args(args: str) -> list[str]:
    out: list[str] = []
    cur: list[str] = []
    depth = 0
    quote: str | None = None
    escape = False
    for ch in args:
        if quote:
            cur.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            cur.append(ch)
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        out.append(tail)
    return out


def unquote_c_string(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    match = re.fullmatch(r'L?"((?:\\.|[^"\\])*)"', value)
    if not match:
        return None
    return bytes(match.group(1), "utf-8").decode("unicode_escape", errors="replace")


def find_enclosing_function(source: str, offset: int) -> str | None:
    prefix = source[:offset]
    pattern = re.compile(r"(?m)^[A-Za-z_][\w\s\*\(\),]*?\s+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{")
    last: str | None = None
    for match in pattern.finditer(prefix):
        name = match.group(1)
        if name not in {"if", "for", "while", "switch"}:
            last = name
    return last


def line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def extract_balanced_call(source: str, start: int) -> tuple[str, int] | None:
    open_paren = source.find("(", start)
    if open_paren < 0:
        return None
    depth = 0
    quote: str | None = None
    escape = False
    for index in range(open_paren, len(source)):
        ch = source[index]
        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return source[start : index + 1], index + 1
    return None
