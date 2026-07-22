#!/usr/bin/env python3
r"""Flatten a section-per-file LaTeX draft into one self-contained .tex.

Two jobs, both needed before the manuscript is handed to a downstream tool:

1. Inline every ``\input{...}`` / ``\include{...}`` relative to the main file, so
   the result is one self-contained document with no path-resolution risk.
2. Rewrite compile-unsafe one-line footnote citation slots
   ``\footnote{% CITE: ...}`` into the brace-safe two-line form. On one line the
   ``%`` comments out the closing ``}``; that unbalanced brace both breaks
   ``pdflatex`` and makes comment-stripping parsers (e.g. lit-review-orchestrator)
   brace-match past the footnote and swallow whole sections.

Usage:
    python assemble_manuscript.py --main path/to/main.tex [--out combined.tex]

The brace report is computed on a comment-stripped copy (what a parser sees), so
"balanced" there means the flattened file is safe for the downstream pipeline.
"""
import argparse
import pathlib
import re
import sys

INPUT_RE = re.compile(r'\\(?:input|include)\{([^}]+)\}')
FN_SLOT_RE = re.compile(r'\\footnote\{%([^\n}]*)\}')  # one-line slot; } after the %


def inline(text: str, base: pathlib.Path, depth: int = 0) -> str:
    if depth > 8:
        return text

    def repl(m):
        name = m.group(1).strip()
        for cand in (base / name, base / (name + ".tex")):
            if cand.is_file():
                return inline(cand.read_text(encoding="utf-8"), cand.parent, depth + 1)
        return m.group(0)  # leave an unresolved input untouched

    return INPUT_RE.sub(repl, text)


def normalize_footnote_slots(text: str) -> str:
    return FN_SLOT_RE.sub(lambda m: "\\footnote{%\n%" + m.group(1) + "\n}", text)


def strip_comments(text: str) -> str:
    """Drop each line from its first unescaped % — mirrors a de-TeX parser."""
    out = []
    for line in text.split("\n"):
        res = []
        for i, ch in enumerate(line):
            if ch == "%" and (i == 0 or line[i - 1] != "\\"):
                break
            res.append(ch)
        out.append("".join(res))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", required=True, help="path to main.tex")
    ap.add_argument("--out", help="output path (default: combined.tex beside main)")
    a = ap.parse_args()
    mainp = pathlib.Path(a.main).resolve()
    out = pathlib.Path(a.out).resolve() if a.out else mainp.with_name("combined.tex")

    text = inline(mainp.read_text(encoding="utf-8"), mainp.parent)
    n_fixed = len(FN_SLOT_RE.findall(text))
    text = normalize_footnote_slots(text)
    out.write_text(text, encoding="utf-8")

    stripped = strip_comments(text)
    op, cl = stripped.count("{"), stripped.count("}")
    unresolved = len(INPUT_RE.findall(text))
    print(f"assembled -> {out}")
    print(f"  sections: {text.count(chr(92) + 'section{')}"
          f"  footnote slots fixed: {n_fixed}"
          f"  unresolved input/include: {unresolved}")
    print(f"  braces (comment-stripped): {{ {op}  }} {cl}  "
          f"{'balanced — parser-safe' if op == cl else 'UNBALANCED — stray %...} line remains'}")
    return 0 if op == cl and unresolved == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
