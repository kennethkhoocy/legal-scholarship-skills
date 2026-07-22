# -*- coding: utf-8 -*-
"""Generic helpers for full-tabular table conversion.

The former label-specific batch builder has been replaced by convert.py's
per-float routing. This module keeps small helper functions available for
interactive use and exposes a CLI that builds one full tabular into a DOCX.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from docx import Document

import tex_table_to_docx as T
from full_tabular_to_docx import add_fulltabular_table, parse_fulltabular


def brace(s: str, open_idx: int) -> tuple[str, int]:
    depth = 0
    i = open_idx
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            i += 2
            continue
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return s[open_idx + 1 : i], i + 1
        i += 1
    return s[open_idx + 1 :], len(s)


def arg(block: str, cmd: str) -> str | None:
    m = re.search(r"\\" + re.escape(cmd) + r"\s*\{", block)
    if not m:
        return None
    return brace(block, m.end() - 1)[0]


def table_blocks(tex: str):
    for m in re.finditer(r"\\begin\{(table|sidewaystable)\}(\[[^\]]*\])?", tex):
        env = m.group(1)
        end_pat = rf"\\end\{{{env}\}}"
        end_m = re.search(end_pat, tex[m.end() :])
        if not end_m:
            continue
        start = m.end()
        end = m.end() + end_m.start()
        yield env, tex[start:end]


def block_for_label(tex: str, label: str) -> tuple[str, str] | tuple[None, None]:
    for env, block in table_blocks(tex):
        if arg(block, "label") == label:
            return env, block
    return None, None


def strip_outer_braces(s: str) -> str:
    s = s.strip()
    if s.startswith("{"):
        inner, end = brace(s, 0)
        if not s[end:].strip():
            return inner.strip()
    return s


def clean_notes(notes: str | None) -> str:
    if not notes:
        return ""
    s = notes.strip()
    s = re.sub(r"\\begin\{minipage\}\{[^{}]*\}", "", s)
    s = s.replace(r"\end{minipage}", "")
    s = s.strip()
    if s.startswith(r"\footnotesize"):
        s = s[len(r"\footnotesize") :].strip()
    s = strip_outer_braces(s)
    s = re.sub(r"^\\vspace\{[^{}]*\}", "", s).strip()
    return s


def extract_notes_from_block(block: str) -> str:
    m = re.search(r"\\begin\{minipage\}\{[^{}]*\}", block)
    if not m:
        return ""
    end_m = re.search(r"\\end\{minipage\}", block[m.end() :])
    if not end_m:
        return ""
    return clean_notes(block[m.end() : m.end() + end_m.start()])


def extract_tabular_from_block(block: str) -> str:
    m = re.search(r"\\begin\{(tabular|tabulary|tabularx|longtable)\}", block)
    if not m:
        raise ValueError("block does not contain a supported tabular environment")
    env = m.group(1)
    end_m = re.search(rf"\\end\{{{env}\}}", block[m.end() :])
    if not end_m:
        raise ValueError(f"block does not close {env}")
    return block[m.start() : m.end() + end_m.end()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build one native DOCX table from a full tabular source.")
    parser.add_argument("tabular_tex")
    parser.add_argument("out")
    parser.add_argument("--caption", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--font", default="Linux Libertine G")
    parser.add_argument("--avail-in", type=float, default=6.4)
    ns = parser.parse_args()

    T.set_font(ns.font) if hasattr(T, "set_font") else setattr(T, "FONT", ns.font)
    tabular = Path(ns.tabular_tex).read_text(encoding="utf-8", errors="replace")
    parsed = parse_fulltabular(tabular)
    doc = Document()
    T._setup_doc(doc)
    add_fulltabular_table(doc, tabular, ns.caption, ns.notes, avail_in=ns.avail_in)
    doc.save(ns.out)
    print(f"rows={len(parsed.rows)} cols={len(parsed.columns)} out={ns.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
