"""Remove garbled text fragments from extracted Markdown.

Born-digital vector figures (plots, phase diagrams, flow charts) carry their
axis and region labels in the PDF text layer. Layout parsers crop the figure to
an image but ALSO place those labels into the Markdown text stream in reading
order, producing a run of short, disconnected, often mojibake fragments wedged
between the figure's image and its caption. For example:

    ![image](...)
    (d)
    Liability
    Full  Deterrence
    {3 *
    =  0
    Prob. Informed (rr)
    Âo
    Figure 1: Equilibrium Characterization

The figure image and caption are the good representation; the fragments are
redundant noise. This module detects such runs and removes them while protecting
real content: LaTeX math ($$...$$ and inline $...$), fenced code, headings,
tables, lists, block quotes, images, captions, and ordinary prose sentences.

It is intentionally conservative — a run is removed only when it is both
fragment-dense AND either (a) adjacent to a figure image/caption or (b) long and
rich in "junk" tokens (lone operators, brace/slash-digit garble, mojibake). When
in doubt, content is kept.

Usage:
    python clean_garbled_fragments.py <input.md> [--in-place | -o OUT.md] [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# --- line classifiers ---------------------------------------------------------

CAPTION_RE = re.compile(r"^\s*(Figure|Fig\.?|Table|Tbl\.?|Panel|Scheme|Exhibit|Chart)\s*\.?\s*\d", re.IGNORECASE)
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")
IMAGE_RE = re.compile(r"!\[")
LIST_RE = re.compile(r"^\s*([-*+]|\d+[.)])\s+\S")
BLOCKQUOTE_RE = re.compile(r"^\s*>")
HTML_RE = re.compile(r"^\s*<[A-Za-z!/]")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
SENTENCE_END = (".", "?", "!", ":", ";", '."', '.)', '.”')

# "Junk" tokens characteristic of garbled vector-figure text.
JUNK_RES = [
    re.compile(r"^[^A-Za-z0-9]{1,4}$"),                       # pure symbols: "=", "{", "**"
    re.compile(r"^[\(\[\{]?\s*[A-Za-z]\s*[\)\]\}\*]?$"),      # "(d)", "d", "d*"
    re.compile(r"\{\s*\d|/\s*\d|_\s*\("),                     # "{3", "/3", "_("  (β*, π garble)
    re.compile(r"^[=≤≥<>±∓+\-*/×·∗∈]\s*[\d*]*\s*$"),           # "= 0", "= 1", "=", "± *"
    re.compile(r"\(rr\)|\(0,\s*1\)|E\s*\(0,\s*1\)"),          # garbled greek / interval labels
    re.compile(r"^[ÂÃÄÅÆÇÈÊÎÏÔÛÝ]\w{0,4}$"),                   # mojibake-led "Âo"
]


# Private-Use-Area glyphs (U+E000–U+F8FF) are font-private codepoints — leaked
# math symbols (the large brace of a cases environment, integral/sum operators,
# fraction bars) that a born-digital parser drops into the text stream when it
# cannot map them to Unicode. They are never legitimate content in an extracted
# academic paper, so a line that is ENTIRELY such glyphs is pure debris. The
# garbled-run logic below only removes a line when it sits inside a qualifying
# run, so a lone leaked glyph — e.g. the U+F8F1 brace stranded on its own line
# just above a `$$ … \begin{cases}` block — slips through. Strip those here,
# unconditionally and before run detection.
# ponytail: whole-PUA lines only. An inline leaked glyph mid-prose is left for
# the math sanitizer / verify_extraction.py to surface, rather than risk nuking
# a character that turns out to be real.
_PUA_LINE_RE = re.compile(r"^[-\s]+$")


def _strip_pua_lines(text: str) -> tuple[str, int]:
    """Drop lines whose only non-whitespace content is private-use glyphs."""
    out: list[str] = []
    removed = 0
    for line in text.split("\n"):
        if line.strip() and _PUA_LINE_RE.match(line):
            removed += 1
            continue
        out.append(line)
    return "\n".join(out), removed


def _is_blank(s: str) -> bool:
    return s.strip() == ""


def _is_sentence(s: str) -> bool:
    t = s.strip()
    return len(t.split()) >= 5 and t.endswith(SENTENCE_END)


def _is_fragment(s: str, short_len: int = 26, max_words: int = 4) -> bool:
    t = s.strip()
    if not t:
        return False
    return len(t) <= short_len and len(t.split()) <= max_words


def _is_noise(s: str, max_len: int = 50, min_alnum_ratio: float = 0.4) -> bool:
    """A short line that is mostly non-alphanumeric — vector-stroke / line-art
    debris a parser misreads as text (e.g. ``~- · · ··· - -- -``,
    ``1-<;;:::---~...,._``). Pipe-bearing lines are excluded so real table rows
    and separators are never treated as noise.
    """
    t = s.strip()
    if not t or len(t) > max_len or "|" in t:
        return False
    alnum = sum(c.isalnum() for c in t)
    return alnum / len(t) < min_alnum_ratio


def _is_removable(s: str) -> bool:
    """A line eligible to belong to (and be removed with) a garbled run."""
    return _is_fragment(s) or _is_noise(s)


def _is_junk(s: str) -> bool:
    t = s.strip()
    if len(t) <= 3 or _is_noise(t):
        return True
    return any(r.search(t) for r in JUNK_RES)


def _is_boundary(s: str) -> bool:
    """Structural lines that must never be removed and that terminate a run.

    Noise lines are excluded: line-art debris can start with ``-`` (looks like a
    list item) without being one, so such lines stay removable.
    """
    if _is_noise(s):
        return False
    return bool(
        HEADING_RE.match(s)
        or TABLE_RE.match(s)
        or IMAGE_RE.search(s)
        or CAPTION_RE.match(s)
        or LIST_RE.match(s)
        or BLOCKQUOTE_RE.match(s)
        or HTML_RE.match(s)
        or FENCE_RE.match(s)
    )


def _protected_mask(lines: list[str]) -> list[bool]:
    """Mark lines inside fenced code blocks or $$...$$ math blocks as protected."""
    n = len(lines)
    mask = [False] * n
    in_code = False
    in_math = False
    for idx, line in enumerate(lines):
        s = line.strip()
        if in_code:
            mask[idx] = True
            if FENCE_RE.match(s):
                in_code = False
            continue
        if in_math:
            mask[idx] = True
            if s.endswith("$$") or s == "$$":
                in_math = False
            continue
        if FENCE_RE.match(s):
            in_code = True
            mask[idx] = True
            continue
        if s == "$$" or (s.startswith("$$") and not s.endswith("$$")):
            in_math = True
            mask[idx] = True
            continue
    return mask


def _prev_nonblank(lines: list[str], idx: int) -> int | None:
    while idx >= 0:
        if not _is_blank(lines[idx]):
            return idx
        idx -= 1
    return None


def _next_nonblank(lines: list[str], idx: int, n: int) -> int | None:
    while idx < n:
        if not _is_blank(lines[idx]):
            return idx
        idx += 1
    return None


def _qualifies(lines, content_idx, start, end, n) -> bool:
    """Decide whether a run of fragment lines is garbled figure text to remove."""
    m = len(content_idx)
    if m == 0:
        return False
    frags = sum(1 for k in content_idx if _is_removable(lines[k]))
    junks = sum(1 for k in content_idx if _is_junk(lines[k]))
    frac = frags / m
    if frac < 0.7:
        return False

    prev = _prev_nonblank(lines, start - 1)
    nxt = _next_nonblank(lines, end, n)
    figure_adjacent = (
        (prev is not None and IMAGE_RE.search(lines[prev]))
        or (nxt is not None and (CAPTION_RE.match(lines[nxt]) or IMAGE_RE.search(lines[nxt])))
    )

    # Figure-adjacent runs are almost certainly leaked labels: a low bar.
    if figure_adjacent and m >= 3 and junks >= 1:
        return True
    # Free-standing runs: demand length and strong junk evidence.
    if not figure_adjacent and m >= 6 and junks >= 2:
        return True
    return False


def clean(text: str) -> tuple[str, list[dict]]:
    """Return (cleaned_text, removed_runs). Each removed run is a small report dict."""
    text, pua_removed = _strip_pua_lines(text)
    lines = text.split("\n")
    n = len(lines)
    protected = _protected_mask(lines)
    remove = [False] * n
    reports: list[dict] = []
    if pua_removed:
        reports.append({
            "start_line": 0,
            "end_line": 0,
            "num_fragments": pua_removed,
            "sample": f"<{pua_removed} stray private-use glyph line(s) removed>",
        })

    i = 0
    while i < n:
        if (
            _is_blank(lines[i])
            or protected[i]
            or _is_boundary(lines[i])
            or _is_sentence(lines[i])
            or not _is_removable(lines[i])
        ):
            i += 1
            continue

        # Grow a run of fragment/noise lines, allowing blank separators.
        start = i
        content_idx: list[int] = []
        j = i
        while j < n:
            if protected[j]:
                break
            if _is_blank(lines[j]):
                j += 1
                continue
            if _is_boundary(lines[j]) or _is_sentence(lines[j]) or not _is_removable(lines[j]):
                break
            content_idx.append(j)
            j += 1
        end = j  # exclusive

        if _qualifies(lines, content_idx, start, end, n):
            last = content_idx[-1]
            for k in range(start, last + 1):
                remove[k] = True
            reports.append({
                "start_line": start + 1,
                "end_line": last + 1,
                "num_fragments": len(content_idx),
                "sample": " | ".join(lines[k].strip() for k in content_idx[:6]),
            })
            i = end
        else:
            i = end if end > i else i + 1

    kept = [lines[k] for k in range(n) if not remove[k]]
    cleaned = "\n".join(kept)
    # Collapse runs of 3+ blank lines (left by removals) down to a single blank.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, reports


def _selfcheck() -> None:
    """Assert PUA-line stripping removes leaked glyphs and spares real content."""
    brace = ""  # the cases-environment brace glyph seen in the wild
    src = f"Some prose before.\n\n{brace}\n\n$$\nx = 1\n$$\n\n--- a real rule ---\n0.137"
    cleaned, reports = clean(src)
    assert brace not in cleaned, "stray PUA glyph not removed"
    assert "Some prose before." in cleaned and "x = 1" in cleaned, "real content dropped"
    assert "--- a real rule ---" in cleaned and "0.137" in cleaned, "dash/number line wrongly dropped"
    assert any(r["sample"].startswith("<") and "private-use" in r["sample"] for r in reports), "no PUA report"
    # idempotent: a second pass removes nothing further
    again, reports2 = clean(cleaned)
    assert again == cleaned and not any("private-use" in r["sample"] for r in reports2), "not idempotent"
    print("ok: PUA-line strip removes glyphs, spares prose/math/dashes/numbers, idempotent")


def main() -> None:
    if "--selfcheck" in sys.argv:
        _selfcheck()
        return
    ap = argparse.ArgumentParser(description="Strip garbled vector-figure text fragments from Markdown.")
    ap.add_argument("input_path", help="Markdown file to clean")
    ap.add_argument("-o", "--output", default=None, help="Write cleaned output here (default: stdout)")
    ap.add_argument("--in-place", action="store_true", help="Overwrite the input file in place")
    ap.add_argument("--dry-run", action="store_true", help="Report what would be removed; write nothing")
    ap.add_argument("-q", "--quiet", action="store_true", help="Suppress the removal report on stderr")
    args = ap.parse_args()

    path = Path(args.input_path)
    if not path.exists():
        print(f"ERROR: {path} does not exist", file=sys.stderr)
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    cleaned, reports = clean(text)

    if not args.quiet:
        removed_lines = sum(r["num_fragments"] for r in reports)
        print(
            f"[clean] {len(reports)} garbled run(s), {removed_lines} fragment line(s) removed",
            file=sys.stderr,
        )
        for r in reports:
            print(f"  lines {r['start_line']}-{r['end_line']}: {r['sample']}", file=sys.stderr)

    if args.dry_run:
        return
    if args.in_place:
        path.write_text(cleaned, encoding="utf-8")
    elif args.output:
        Path(args.output).write_text(cleaned, encoding="utf-8")
    else:
        sys.stdout.write(cleaned)


if __name__ == "__main__":
    main()
