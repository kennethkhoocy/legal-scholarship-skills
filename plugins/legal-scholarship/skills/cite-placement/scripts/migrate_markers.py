#!/usr/bin/env python3
"""
Retroactively add %CITE-PLACED markers to all \\footnote{} commands in a .tex file.

One-time migration script for manuscripts produced before the marker feature
was added. Adds the marker to every footnote that doesn't already have one.

Usage:
    python migrate_markers.py input.tex [output.tex]

If output.tex is omitted, overwrites input.tex (with a .bak backup first).
"""

import re
import shutil
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


def process(input_path: str, output_path: str) -> tuple[int, int]:
    """Add %CITE-PLACED markers to all unmarked footnotes.

    Returns (tagged_count, already_tagged_count).
    """
    tex = Path(input_path).read_text(encoding="utf-8")

    pattern = re.compile(r"\\footnote\{")
    insertions: list[tuple[int, str]] = []
    already_tagged = 0

    for m in pattern.finditer(tex):
        content_start = m.end()

        # Check if already has the marker
        after_brace = tex[content_start:content_start + len(MARKER)]
        if after_brace == MARKER:
            already_tagged += 1
            continue

        # Verify this is a valid footnote (has matching closing brace)
        end = find_footnote_end(tex, content_start)
        if end is None:
            continue

        # Queue insertion of marker after the opening brace
        insertions.append((content_start, MARKER + "\n"))

    if not insertions:
        print(f"No unmarked footnotes found. Already tagged: {already_tagged}.")
        if input_path != output_path:
            Path(output_path).write_text(tex, encoding="utf-8")
        return (0, already_tagged)

    # Apply insertions in reverse order to preserve positions
    for pos, text in reversed(insertions):
        tex = tex[:pos] + text + tex[pos:]

    Path(output_path).write_text(tex, encoding="utf-8")

    print(f"Tagged {len(insertions)} footnotes with %CITE-PLACED marker.")
    print(f"Already tagged: {already_tagged}.")
    print(f"Output: {output_path}")

    return (len(insertions), already_tagged)


def main():
    if len(sys.argv) < 2:
        print("Usage: python migrate_markers.py input.tex [output.tex]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    if not Path(input_path).is_file():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        # In-place mode: create backup first
        backup_path = input_path + ".bak"
        shutil.copy2(input_path, backup_path)
        print(f"Backup saved to: {backup_path}")
        output_path = input_path

    process(input_path, output_path)


if __name__ == "__main__":
    main()
