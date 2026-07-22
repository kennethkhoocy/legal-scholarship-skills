"""Post-extraction quality gate for Markdown produced by the pdf skill.

The skill's verification checklist (extraction.md §8) is passive prose — it
relies on the operator *noticing* problems. The failure modes that actually slip
through on born-digital academic papers (finance/econ journal articles in
particular) are silent: Docling's table model merges dense regression-table rows,
its formula model flattens or garbles multi-line equations, and the occasional
font private-use glyph survives. None of these throw; the output just looks
plausible. This script makes the checklist executable so those failures are
surfaced with line numbers instead of shipped.

It is a DETECTOR, not a fixer. For each issue it points at the line and says what
to do (rebuild the table positionally per extraction.md §4C; hand-fix or escalate
the equation; the glyph is auto-stripped by clean_garbled_fragments now). It is
tuned for high precision — a flag should almost always be a real problem — so a
clean report is meaningful.

Usage:
    python verify_extraction.py <file.md> [--probe probe.json] [--quiet]
Exit code: 0 = clean, 1 = issues found (so it can gate a pipeline).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

PUA = lambda c: 0xE000 <= ord(c) <= 0xF8FF

# A numeric value token in an econ table: 0.137, 1.47m, 1.359 ∗∗∗ (0.310), (0.052)
_VALUE = re.compile(r"-?\d[\d.,]*\s*[a-z%]*\s*[∗*]{0,3}\s*(?:\([\d.,]+\))?")
_SE_THEN_MORE = re.compile(r"\)\s+\S")          # a closed (SE) immediately followed by more content
_TWO_PARENS = re.compile(r"\([\d.,]+\).*\([\d.,]+\)")  # two parenthetical groups in one cell
_FLAGS = re.compile(r"\b(Yes|No)\b")
# A bare numeric token: 0.7396, 1,528,422, 42.43%, (0.310), -0.05, 0.137***.
# A *run* of these separated only by whitespace inside ONE cell is a vertical-spill
# merge — a whole column's values collapsed into a single cell (the Table 6 case:
# "0.7396 0.7063 0.6956 0.6331 0.5782 …"). This pattern slips past the other table
# checks: the prose-word guard clears it (a spilled numeric column carries no
# prose), and the two-value guard misses it (bare decimals have no parentheses for
# _SE_THEN_MORE / _TWO_PARENS to catch).
_NUM_TOKEN = re.compile(r"^\(?[-+]?\$?\d[\d,]*\.?\d*%?\)?[∗*]{0,3}$")
_SPILL_MIN_RUN = 5  # >= this many consecutive numeric tokens in one cell => spill


def _max_numeric_run(cell: str) -> int:
    """Longest run of consecutive whitespace-separated numeric tokens in a cell.

    Counts a *run* (numbers adjacent with no intervening word), not a raw count,
    so a prose cell that merely mentions several numbers — e.g. a definitions cell
    "an index from 0 to 1 … over 1980 to 2005 (… 2018)" — stays at a run of 1
    (its numbers are separated by words) and is never mistaken for a spill.
    """
    run = best = 0
    for tok in cell.split():
        if _NUM_TOKEN.match(tok):
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


# Math signals for spotting display equations left as plain text.
_MATH_SIGNAL = re.compile(
    r"[=Φφθγµλαβπσ∑∫∈≥≤≠×·±√]|\\[A-Za-z]+|\b\w_\{|\^\{|\b[A-Za-z]\s*_\s*\{?\s*i\s*t\b"
)


def _tables(lines: list[str]) -> list[tuple[int, list[str]]]:
    """Yield (line_no, cells) for each pipe-table data row (skips separator rows)."""
    out = []
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if not (s.startswith("|") and s.endswith("|") and s.count("|") >= 2):
            continue
        if re.fullmatch(r"\|[\s:|-]+\|", s):  # |---|---| separator
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        out.append((i, cells))
    return out


def check_pua(text: str) -> list[dict]:
    issues = []
    for i, ln in enumerate(text.split("\n"), 1):
        pua = sorted({c for c in ln if PUA(c)})
        if pua:
            names = ", ".join(f"U+{ord(c):04X}" for c in pua)
            issues.append({"line": i, "kind": "stray-glyph", "detail": names,
                           "fix": "leaked font private-use glyph; whole-PUA lines are auto-stripped now — "
                                  "an inline one means a flattened equation: hand-fix that line"})
    return issues


def check_tables(lines: list[str]) -> list[dict]:
    issues = []
    for ln_no, cells in _tables(lines):
        for col, cell in enumerate(cells):
            # A merged regression-table cell is numeric-dominated debris
            # ("1.359 ∗∗∗ (0.310) 0.572"). A legitimate cell in a *definitions*
            # table is long prose with embedded math. Distinguish them by prose
            # word count so a rich description cell is never mistaken for a merge.
            prose_words = [w for w in re.findall(r"[A-Za-z]{3,}", cell) if w not in ("Yes", "No")]
            numeric_dominated = len(prose_words) <= 3
            # vertical-spill: a whole column's values collapsed into one cell as a
            # run of bare numbers ("0.7396 0.7063 0.6956 …"). Checked independently
            # of numeric_dominated, because the spilled numeric columns carry no
            # prose AND a mixed label+number cell can also strand a numeric run.
            if col >= 1:
                run = _max_numeric_run(cell)
                if run >= _SPILL_MIN_RUN:
                    issues.append({"line": ln_no, "kind": "merged-table-row",
                                   "detail": f"col {col+1}: {run} stacked values — {cell[:60]!r}…",
                                   "fix": "vertical-spill — a whole column's values collapsed into one cell; "
                                          "render this table with render_region.py and rewrite it from the "
                                          "image (extraction.md §4C)"})
                    break
            # data cell carrying two stacked values (the classic vertical-spill merge)
            if col >= 1 and numeric_dominated:
                vals = _VALUE.findall(cell)
                two_values = len([v for v in vals if v.strip()]) >= 2 and (
                    _SE_THEN_MORE.search(cell) or _TWO_PARENS.search(cell)
                )
                two_flags = len(_FLAGS.findall(cell)) >= 2
                flag_after_value = bool(re.search(r"\d\s*[a-z%]*\s+(Yes|No)\b", cell))
                if two_values or two_flags or flag_after_value:
                    issues.append({"line": ln_no, "kind": "merged-table-row",
                                   "detail": f"col {col+1}: {cell!r}",
                                   "fix": "Docling merged two rows into one cell; render this table with "
                                          "render_region.py and rewrite it from the image (extraction.md §4C)"})
                    break
            # label cell carrying two stacked labels: "Market Cap (log) R-squared"
            if col == 0 and _FLAGS.search(cell) and len(cell.split()) >= 3:
                issues.append({"line": ln_no, "kind": "merged-table-row",
                               "detail": f"label col: {cell!r}",
                               "fix": "label cell contains a Yes/No flag — two rows merged; render the table "
                                      "with render_region.py and rewrite it from the image (extraction.md §4C)"})
                break
    return issues


def check_equations(text: str, formula_density: float | None) -> list[dict]:
    issues = []
    lines = text.split("\n")
    # 1. $$ blocks that are empty or contain known-garbage macros
    in_block, start, body = False, 0, []
    dollar_blocks = 0
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if s == "$$" and not in_block:
            in_block, start, body = True, i, []
        elif s == "$$" and in_block:
            in_block = False
            dollar_blocks += 1
            joined = " ".join(body).strip()
            if not joined:
                issues.append({"line": start, "kind": "broken-equation", "detail": "empty $$ block",
                               "fix": "equation was suppressed/garbled; hand-rebuild from the source PDF"})
            elif "\\intertext" in joined or joined.count("\\intertext") >= 1:
                issues.append({"line": start, "kind": "broken-equation",
                               "detail": "$$ block is \\intertext debris",
                               "fix": "formula model failed on a multi-line/cases equation; hand-rebuild "
                                      "(\\begin{cases}) or escalate to lightonocr"})
        elif in_block:
            body.append(s)
    # 2. high formula density but equations look flattened to plain text
    if formula_density is not None and formula_density > 0.2:
        in_dollar = False
        flat = []
        for i, ln in enumerate(lines, 1):
            s = ln.strip()
            if s.startswith("$$"):
                in_dollar = not in_dollar if s == "$$" else in_dollar
                continue
            if in_dollar or s.startswith("|") or s.startswith("#") or s.startswith("!["):
                continue
            # a plain line dense in math signals, not wrapped in $…$
            if "$" in s:
                continue
            sig = len(_MATH_SIGNAL.findall(s))
            if sig >= 4 and len(s) < 200 and any(g in s for g in "Φθγµλαβ=≥×"):
                flat.append((i, s))
        if flat and dollar_blocks <= 1:
            for i, s in flat[:8]:
                issues.append({"line": i, "kind": "flattened-equation",
                               "detail": (s[:90] + "…") if len(s) > 90 else s,
                               "fix": f"formula_density={formula_density:.2f} but only {dollar_blocks} $$ "
                                      "block(s): equations likely flattened to text. Render the region "
                                      "(render_region.py) and rewrite the LaTeX from the image; "
                                      "--hybrid-mode full helps simple eqs, lightonocr for image equations"})
    return issues


def verify(text: str, formula_density: float | None = None) -> list[dict]:
    if not text.strip():
        return [{"line": 1, "kind": "empty-output",
                 "detail": "extraction output is empty/whitespace-only",
                 "fix": "the backend produced nothing — re-run it, check the page "
                        "selection, or escalate to lightonocr (scripts/lightonocr_run.py)"}]
    return check_pua(text) + check_tables(text.split("\n")) + check_equations(text, formula_density)


def _selfcheck() -> None:
    merged = "| |(1)|(2)|(3)|\n|---|---|---|---|\n|Market Cap (log) R-squared|0.216|0.444|1.359 ∗∗∗ (0.310) 0.572|\n|Observations Country FE|1.47m|1.47m Yes Yes|1.44m Yes Yes|"
    clean = "| |(1)|(2)|\n|---|---|---|\n|Free float|0.137|0.101|\n|Country FE|No|Yes|"
    assert any(x["kind"] == "merged-table-row" for x in check_tables(merged.split("\n"))), "missed merged row"
    assert not check_tables(clean.split("\n")), f"false positive on clean table: {check_tables(clean.split(chr(10)))}"
    # vertical-spill: a whole column collapsed into one cell (the Table 6 failure)
    spill = "|Macro|Sector|κ|\n|---|---|---|\n|United States| |0.7396 0.7063 0.6956 0.6331 0.5782 0.5666|"
    assert any(x["kind"] == "merged-table-row" for x in check_tables(spill.split("\n"))), "missed vertical-spill"
    # a definitions cell that merely MENTIONS several numbers must NOT trip the spill check
    defs = "|Variable|Definition|\n|---|---|\n|CLI|An index from 0 to 1 over the period 1980 to 2005 (Chilton 2018).|"
    assert not check_tables(defs.split("\n")), f"false positive on definitions cell: {check_tables(defs.split(chr(10)))}"
    assert check_pua("brace  here"), "missed PUA"
    assert not check_pua("normal text 0.137"), "PUA false positive"
    garbage = "$$\n\\intertext { l } \\intertext { x } \\intertext { o r w i s }\n$$"
    assert any(x["kind"] == "broken-equation" for x in check_equations(garbage, 0.6)), "missed intertext garbage"
    flat = "I _ { it } = \\Phi \\theta Turnover + \\gamma Holdings ≥ 2.66 × x = 0"
    assert any(x["kind"] == "flattened-equation" for x in check_equations(flat, 0.6)), "missed flattened eq"
    assert not check_equations("Just ordinary prose about funds and ownership.", 0.6), "prose flagged as equation"
    print("ok: detector flags merged rows / glyphs / broken+flattened equations, spares clean content")


def main() -> None:
    if "--selfcheck" in sys.argv:
        _selfcheck()
        return
    ap = argparse.ArgumentParser(description="Quality gate for pdf-skill Markdown output.")
    ap.add_argument("input_path", help="Markdown file to verify")
    ap.add_argument("--probe", default=None, help="probe_pdf.py JSON (enables formula-density-aware checks)")
    ap.add_argument("--quiet", action="store_true", help="Only print the summary line")
    args = ap.parse_args()

    fd = None
    if args.probe and Path(args.probe).exists():
        try:
            fd = json.loads(Path(args.probe).read_text(encoding="utf-8")).get("formula_density")
        except (json.JSONDecodeError, OSError):
            pass

    text = Path(args.input_path).read_text(encoding="utf-8")
    issues = verify(text, fd)

    by_kind: dict[str, int] = {}
    for it in issues:
        by_kind[it["kind"]] = by_kind.get(it["kind"], 0) + 1
    if not args.quiet:
        for it in sorted(issues, key=lambda x: x["line"]):
            print(f"  L{it['line']:>4}  [{it['kind']}] {it['detail']}\n         → {it['fix']}")
    if issues:
        summary = ", ".join(f"{n} {k}" for k, n in sorted(by_kind.items()))
        print(f"[verify] {len(issues)} issue(s): {summary}")
        sys.exit(1)
    print("[verify] clean — no merged tables, broken equations, or stray glyphs detected")


if __name__ == "__main__":
    main()
