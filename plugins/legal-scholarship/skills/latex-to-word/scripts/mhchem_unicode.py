# -*- coding: utf-8 -*-
r"""Small mhchem ``\ce{...}`` renderer for pre-pandoc conversion.

The converter only needs a conservative subset of mhchem: ordinary formulae,
charges, coefficients, simple reaction arrows, states, and hydrate dots.  The
functions here return plain Unicode text so Pandoc never sees raw ``\ce``.
"""
from __future__ import annotations

import re


SUBSCRIPT_DIGITS = str.maketrans(
    "0123456789",
    "\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089",
)
SUPERSCRIPT_CHARS = {
    "0": "\u2070",
    "1": "\u00b9",
    "2": "\u00b2",
    "3": "\u00b3",
    "4": "\u2074",
    "5": "\u2075",
    "6": "\u2076",
    "7": "\u2077",
    "8": "\u2078",
    "9": "\u2079",
    "+": "\u207a",
    "-": "\u207b",
}

ARROW_REPLACEMENTS = (
    ("<=>>", "\u21cc"),
    ("<<=>", "\u21cc"),
    ("<=>", "\u21cc"),
    ("<->", "\u2194"),
    ("->", "\u2192"),
    ("<-", "\u2190"),
)


def contains_ce_commands(text: str) -> bool:
    return bool(re.search(r"\\ce(?![A-Za-z@])", text))


def _find_matching(text: str, open_pos: int, open_char: str = "{", close_char: str = "}") -> int:
    depth = 0
    escaped = False
    for pos in range(open_pos, len(text)):
        ch = text[pos]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return pos
    raise ValueError(f"No matching {close_char!r} for position {open_pos}")


def _read_group(text: str, open_pos: int) -> tuple[str, int]:
    close_pos = _find_matching(text, open_pos)
    return text[open_pos + 1 : close_pos], close_pos + 1


def _skip_ws(text: str, pos: int) -> int:
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def _replace_arrows(text: str) -> str:
    s = text
    s = re.sub(r"<\s*=\s*>\s*>", "\u21cc", s)
    s = re.sub(r"<\s*<\s*=\s*>", "\u21cc", s)
    s = re.sub(r"<\s*=\s*>", "\u21cc", s)
    s = re.sub(r"<\s*-\s*>", "\u2194", s)
    s = re.sub(r"-\s*>", "\u2192", s)
    s = re.sub(r"<\s*-", "\u2190", s)
    for raw, rendered in ARROW_REPLACEMENTS:
        s = s.replace(raw, rendered)
    return s


def _superscript(text: str) -> str:
    return "".join(SUPERSCRIPT_CHARS.get(ch, ch) for ch in text)


def _previous_nonspace(text: str, pos: int) -> str:
    i = pos - 1
    while i >= 0 and text[i].isspace():
        i -= 1
    return text[i] if i >= 0 else ""


def _next_nonspace(text: str, pos: int) -> str:
    i = pos + 1
    while i < len(text) and text[i].isspace():
        i += 1
    return text[i] if i < len(text) else ""


def _is_charge_sign(text: str, pos: int) -> bool:
    if pos > 0 and text[pos - 1].isspace():
        return False
    prev = _previous_nonspace(text, pos)
    if not prev or prev in "+-\u2190\u2192\u2194\u21cc":
        return False
    nxt = _next_nonspace(text, pos)
    if nxt and not text[pos + 1 : pos + 2].isspace() and (nxt.isalpha() or nxt.isdigit()):
        return False
    return prev.isalnum() or prev in ")]}"


def _is_hydrate_dot(text: str, pos: int) -> bool:
    prev = _previous_nonspace(text, pos)
    nxt = _next_nonspace(text, pos)
    if not prev or not nxt:
        return False
    return (prev.isalnum() or prev in ")]}") and (nxt.isalnum() or nxt in "([")


def render_ce(expr: str) -> str:
    """Render a conservative mhchem expression as plain Unicode text."""
    s = _replace_arrows(expr.strip())
    out: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]

        if ch == "^":
            i += 1
            if i < len(s) and s[i] == "{":
                try:
                    arg, i = _read_group(s, i)
                except ValueError:
                    arg, i = s[i + 1 :], len(s)
            else:
                start = i
                while i < len(s) and (s[i].isdigit() or s[i] in "+-"):
                    i += 1
                arg = s[start:i] if i > start else ""
            out.append(_superscript(arg))
            continue

        if ch.isdigit():
            start = i
            while i < len(s) and s[i].isdigit():
                i += 1
            digits = s[start:i]
            if start > 0 and (s[start - 1].isalpha() or s[start - 1] == ")"):
                out.append(digits.translate(SUBSCRIPT_DIGITS))
            else:
                out.append(digits)
            continue

        if ch in "+-" and _is_charge_sign(s, i):
            out.append(_superscript(ch))
            i += 1
            continue

        if ch == "*":
            out.append("\u00b7")
            i += 1
            continue

        if ch == "." and _is_hydrate_dot(s, i):
            out.append("\u00b7")
            i += 1
            continue

        if ch in "{}":
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def replace_ce_commands(text: str) -> str:
    r"""Replace inline ``\ce{...}`` commands with Unicode, leaving malformed text intact."""
    if not contains_ce_commands(text):
        return text
    command_re = re.compile(r"\\ce(?![A-Za-z@])")
    out: list[str] = []
    pos = 0
    while True:
        match = command_re.search(text, pos)
        if not match:
            out.append(text[pos:])
            break
        arg_pos = _skip_ws(text, match.end())
        if arg_pos >= len(text) or text[arg_pos] != "{":
            out.append(text[pos : match.end()])
            pos = match.end()
            continue
        try:
            content, end = _read_group(text, arg_pos)
        except ValueError:
            out.append(text[pos : match.end()])
            pos = match.end()
            continue
        out.append(text[pos : match.start()])
        out.append(render_ce(content))
        pos = end
    return "".join(out)
