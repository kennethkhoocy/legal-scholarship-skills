#!/usr/bin/env python3
"""
Phase 5 post-processing: Merge adjacent \\footnote{} commands into single footnotes.

Scans the output .tex for adjacent \\footnote{...}\\footnote{...} patterns
(possibly separated by whitespace) and merges them into a single \\footnote{}
with semicolon-delimited citations. This is a safety net — Phase 3c should
handle merging at planning time, but this catches any adjacent footnotes that
slip through from cached plans, incremental additions, or audit-fix insertions.

Must run AFTER all Phase 5 insertions and audit fixes, and BEFORE Phase 6
(short_form.py), since short-form processing depends on final footnote numbering.

Usage:
    python scripts/merge_adjacent_footnotes.py --input Manuscript_cited.tex --output Manuscript_cited.tex
"""

import argparse
import json
import re
import sys
from pathlib import Path


# Default (Bluebook) signals, used when no style config is loaded
_DEFAULT_SIGNALS = [
    "See generally",
    "See also",
    "But see",
    "But cf.",
    "Compare",
    "Cf.",
    "See",
    "E.g.,",
    "Accord",
]

_DEFAULT_MERGE_CONFIG = {
    "separator": "; ",
    "lowercase_signals_after_first": True,
    "end_punctuation": ".",
}

MARKER = "%CITE-PLACED"

# Module-level state set by load_style_config()
_signals: list[str] = list(_DEFAULT_SIGNALS)
_signal_pattern: re.Pattern = re.compile(
    r"^(" + "|".join(re.escape(s) for s in _DEFAULT_SIGNALS) + r")\s",
    re.IGNORECASE,
)
_merge_config: dict = dict(_DEFAULT_MERGE_CONFIG)


def load_style_config(style_id: str, skill_dir: str | None = None) -> None:
    """Load style JSON config, updating module-level signal list and merge rules."""
    global _signals, _signal_pattern, _merge_config

    if skill_dir is None:
        skill_dir = str(Path(__file__).parent.parent)

    style_path = Path(skill_dir) / "references" / "styles" / f"{style_id}.json"
    if not style_path.is_file():
        print(f"  Warning: style config not found: {style_path}, using defaults")
        return

    config = json.loads(style_path.read_text(encoding="utf-8"))
    _signals = config.get("signals", _DEFAULT_SIGNALS)
    _merge_config = {**_DEFAULT_MERGE_CONFIG, **config.get("merge", {})}

    if _signals:
        _signal_pattern = re.compile(
            r"^(" + "|".join(re.escape(s) for s in _signals) + r")\s",
            re.IGNORECASE,
        )
    else:
        _signal_pattern = re.compile(r"(?!)")  # never matches


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


def extract_footnote_content(tex: str, fn_start: int) -> tuple[str, int] | None:
    """Extract the content of a \\footnote{...} starting at fn_start.

    fn_start points to the \\ of \\footnote{.
    Returns (content_inside_braces, end_pos_after_closing_brace) or None.
    """
    prefix = "\\footnote{"
    if tex[fn_start : fn_start + len(prefix)] != prefix:
        return None
    content_start = fn_start + len(prefix)
    end = find_footnote_end(tex, content_start)
    if end is None:
        return None
    content = tex[content_start : end - 1]  # exclude the closing }
    return (content, end)


def lowercase_signal(text: str) -> str:
    """Lowercase the leading signal word in a citation string.

    E.g., "See also Author..." -> "see also Author..."
    """
    m = _signal_pattern.match(text)
    if m:
        signal = m.group(1)
        lowered = signal[0].lower() + signal[1:]
        return lowered + text[len(signal) :]
    return text


def strip_trailing_period(content: str) -> str:
    """Strip the trailing period from footnote content if present."""
    stripped = content.rstrip()
    if stripped.endswith("."):
        return stripped[:-1]
    return stripped


def find_adjacent_footnotes(tex: str) -> list[list[tuple[int, int, str]]]:
    """Find groups of adjacent \\footnote{} commands.

    Returns a list of groups, where each group is a list of
    (start, end, content) tuples for consecutive footnotes
    separated only by whitespace/newlines.
    """
    # Find all \footnote{ positions
    footnote_positions: list[tuple[int, int, str]] = []
    pattern = re.compile(r"\\footnote\{")

    for m in pattern.finditer(tex):
        fn_start = m.start()
        result = extract_footnote_content(tex, fn_start)
        if result is None:
            continue
        content, end = result
        footnote_positions.append((fn_start, end, content))

    if len(footnote_positions) < 2:
        return []

    # Group consecutive footnotes that are adjacent (only whitespace between them)
    groups: list[list[tuple[int, int, str]]] = []
    current_group: list[tuple[int, int, str]] = [footnote_positions[0]]

    for i in range(1, len(footnote_positions)):
        prev_start, prev_end, prev_content = current_group[-1]
        curr_start, curr_end, curr_content = footnote_positions[i]

        # Check if only whitespace/newlines between the end of previous and start of current
        between = tex[prev_end:curr_start]
        if between.strip() == "":
            # Adjacent — add to current group
            current_group.append(footnote_positions[i])
        else:
            # Not adjacent — finalize current group if it has 2+
            if len(current_group) >= 2:
                groups.append(current_group)
            current_group = [footnote_positions[i]]

    # Don't forget the last group
    if len(current_group) >= 2:
        groups.append(current_group)

    return groups


def find_line_number(tex: str, pos: int) -> int:
    """Find the 1-based line number for a character position."""
    return tex[:pos].count("\n") + 1


def strip_marker(content: str) -> str:
    """Strip the %CITE-PLACED marker from footnote content if present."""
    if content.startswith(MARKER + "\n"):
        return content[len(MARKER) + 1:]
    if content.startswith(MARKER):
        return content[len(MARKER):]
    return content


def merge_group(footnotes: list[tuple[int, int, str]]) -> str:
    """Merge a group of adjacent footnote contents into a single footnote body.

    Rules (configurable via style JSON):
    - Citations separated by separator (default "; ")
    - First citation keeps its capitalized signal word
    - Subsequent citations' signal words become lowercase (if style uses signals)
    - End punctuation applied per style config
    - If any constituent footnote had a %CITE-PLACED marker, the merged result
      gets exactly one marker.
    """
    sep = _merge_config.get("separator", "; ")
    lowercase_after_first = _merge_config.get("lowercase_signals_after_first", True)
    end_punct = _merge_config.get("end_punctuation", ".")

    parts: list[str] = []
    has_marker = False

    for i, (start, end, content) in enumerate(footnotes):
        if content.startswith(MARKER):
            has_marker = True
        content = strip_marker(content).strip()
        if i == 0:
            parts.append(strip_trailing_period(content))
        else:
            cleaned = strip_trailing_period(content)
            if lowercase_after_first:
                cleaned = lowercase_signal(cleaned)
            parts.append(cleaned)

    merged = sep.join(parts)
    if end_punct and not merged.endswith(end_punct):
        merged += end_punct

    if has_marker:
        return f"\\footnote{{{MARKER}\n{merged}}}"
    return f"\\footnote{{{merged}}}"


def process(input_path: str, output_path: str, style: str = "bluebook",
            skill_dir: str | None = None) -> int:
    """Process a .tex file, merging adjacent footnotes.

    Returns the number of merge operations performed.
    """
    load_style_config(style, skill_dir)
    tex = Path(input_path).read_text(encoding="utf-8")

    print(f"Phase 5 post-processing: Merging adjacent footnotes (style: {style})")

    groups = find_adjacent_footnotes(tex)

    if not groups:
        print("  No adjacent footnotes found. Nothing to merge.")
        return 0

    total_merged = 0

    # Process groups in reverse order to preserve character positions
    for group in reversed(groups):
        group_start = group[0][0]
        group_end = group[-1][1]
        line_num = find_line_number(tex, group_start)

        # Log the merge
        fn_count = len(group)
        total_merged += 1
        print(
            f"  Merging {fn_count} adjacent footnotes at line {line_num}:"
        )
        for i, (start, end, content) in enumerate(group):
            preview = content[:80].replace("\n", " ")
            if len(content) > 80:
                preview += "..."
            print(f"    [{i + 1}] {preview}")

        # Build the merged footnote
        merged = merge_group(group)

        # Replace the entire group (from first \footnote{ to last }) with the merged version
        tex = tex[:group_start] + merged + tex[group_end:]

    Path(output_path).write_text(tex, encoding="utf-8")

    print(f"  Total merge operations: {total_merged}")
    total_footnotes_consumed = sum(len(g) for g in groups)
    print(
        f"  Footnotes consumed: {total_footnotes_consumed} -> {total_merged} merged footnotes"
    )

    return total_merged


def main():
    parser = argparse.ArgumentParser(
        description="Merge adjacent \\footnote{} commands into single footnotes"
    )
    parser.add_argument("--input", required=True, help="Input .tex file")
    parser.add_argument(
        "--output",
        required=True,
        help="Output .tex file (can be same as input for in-place)",
    )
    parser.add_argument(
        "--style",
        default="bluebook",
        choices=["bluebook", "oscola", "chicago", "apa", "mcgill"],
        help="Citation style (default: bluebook)",
    )
    parser.add_argument(
        "--skill-dir",
        default=None,
        help="Path to cite-placement skill directory",
    )
    args = parser.parse_args()

    if not Path(args.input).is_file():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    merge_count = process(args.input, args.output, args.style, args.skill_dir)
    sys.exit(0 if merge_count >= 0 else 1)


if __name__ == "__main__":
    main()
