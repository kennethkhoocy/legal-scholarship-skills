#!/usr/bin/env python3
"""
Strip all %CITE-PLACED footnotes from a .tex file.

Removes every \\footnote{%CITE-PLACED...} (pipeline-inserted and tagged
pre-existing footnotes), leaving a clean manuscript that can be re-run
through the citation pipeline from scratch.

Footnotes without the %CITE-PLACED marker are left untouched.

Usage:
    python strip_citations.py input.tex [output.tex]

If output.tex is omitted, writes to <input>_stripped.tex.
"""

import re
import sys
from pathlib import Path

MARKER = "%CITE-PLACED"


def find_footnote_end(tex: str, start_after_brace: int) -> int | None:
    """From position after the opening { of \\footnote{, find the matching }.

    Uses brace-depth counting to handle nested braces.
    Returns the index of the character AFTER the closing }, or None if malformed.
    """
    depth = 1
    pos = start_after_brace
    while pos < len(tex) and depth > 0:
        if tex[pos] == "{":
            depth += 1
        elif tex[pos] == "}":
            depth -= 1
        pos += 1
    return pos if depth == 0 else None


def process(input_path: str, output_path: str) -> int:
    """Strip all %CITE-PLACED footnotes from a .tex file.

    Returns the number of footnotes removed.
    """
    tex = Path(input_path).read_text(encoding="utf-8")

    # Find all \footnote{ positions
    pattern = re.compile(r"\\footnote\{")
    removals: list[tuple[int, int]] = []

    for m in pattern.finditer(tex):
        fn_start = m.start()
        content_start = m.end()

        # Check if this footnote has the marker
        after_brace = tex[content_start:content_start + len(MARKER)]
        if after_brace != MARKER:
            continue

        # Find the matching closing brace
        end = find_footnote_end(tex, content_start)
        if end is None:
            continue

        removals.append((fn_start, end))

    if not removals:
        print("No %CITE-PLACED footnotes found. Nothing to strip.")
        Path(output_path).write_text(tex, encoding="utf-8")
        return 0

    # Process removals in reverse order to preserve positions
    for fn_start, fn_end in reversed(removals):
        # Check if removing leaves a double space or trailing space before punctuation
        before = tex[:fn_start]
        after = tex[fn_end:]

        # If there's a space before the footnote and the next char is space/punctuation,
        # remove the leading space to avoid double spaces
        if before and before[-1] == " " and after and after[0] in " \t":
            before = before[:-1]
        elif before and before[-1] == " " and after and after[0] in ".,;:!?)]\n":
            before = before[:-1]

        tex = before + after

    Path(output_path).write_text(tex, encoding="utf-8")

    print(f"Stripped {len(removals)} footnotes with %CITE-PLACED marker.")
    print(f"Output: {output_path}")

    return len(removals)


def main():
    if len(sys.argv) < 2:
        print("Usage: python strip_citations.py input.tex [output.tex]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    if not Path(input_path).is_file():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        p = Path(input_path)
        output_path = str(p.parent / f"{p.stem}_stripped{p.suffix}")

    process(input_path, output_path)


if __name__ == "__main__":
    main()
