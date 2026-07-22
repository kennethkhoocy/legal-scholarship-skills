#!/usr/bin/env python3
"""
Reorder cross-references (supra, Id., hereinafter) after manual footnotes
have been added to the manuscript.

Reads footnote_registry.json (produced by short_form.py) to reverse all
supra/Id. substitutions back to full citations, then re-runs short_form
processing so that footnote numbers are correct.

Usage:
    python scripts/reorder_crossrefs.py --input Manuscript_cited.tex \
        --plan-dir placement/

If --plan-dir is omitted, looks for placement/ alongside the input .tex.
"""

import argparse
import re
import sys
from pathlib import Path

# Import from short_form (same directory)
from short_form import (
    MARKER,
    extract_footnotes,
    find_brace_content,
    parse_footnote_citations,
    process as short_form_process,
)

# ── Registry loading ─────────────────────────────────────────────────

def load_registry(plan_dir: Path) -> dict:
    """Load footnote_registry.json from the placement directory."""
    import json
    reg_path = plan_dir / "footnote_registry.json"
    if not reg_path.is_file():
        print(f"Error: footnote_registry.json not found at {reg_path}", file=sys.stderr)
        print("Run the full pipeline (Phase 6) first to generate the registry.",
              file=sys.stderr)
        sys.exit(1)
    return json.loads(reg_path.read_text(encoding="utf-8"))


# ── Supra/Id. reversal ──────────────────────────────────────────────

# Match: Author, \textit{supra} note N
# or:    Author, \textit{Short Title}, \textit{supra} note N
# Optionally preceded by a signal like "See " or "see also "
SUPRA_PATTERN = re.compile(
    r"(?:(?:See\s+generally|See\s+also|But\s+see|But\s+cf\.|Compare|Cf\.|See|E\.g\.,|Accord)\s+)?"
    r"(.+?),\s*"               # author_key
    r"(?:\\textit\{(.+?)\},\s*)?"  # optional short title
    r"\\textit\{supra\}\s+note\s+(\d+)",
    re.IGNORECASE,
)

ID_PATTERN = re.compile(r"^\\textit\{Id\.\}\.?$")

HEREINAFTER_PATTERN = re.compile(
    r"\s*\[hereinafter\s+\\textit\{[^}]+\}\]",
)


def _build_lookup(registry: dict) -> dict[str, dict]:
    """Build lookup tables from the registry for matching supra references.

    Returns:
        {
            (normalized_author_key, normalized_short_title): work_entry,
            (normalized_author_key, None): work_entry,  # for works without short_title
        }
    """
    lookup: dict[tuple[str, str | None], dict] = {}
    by_author: dict[str, list[dict]] = {}

    for _identity_key, entry in registry.get("works", {}).items():
        author = entry["author_key"].lower().strip()
        by_author.setdefault(author, []).append(entry)

        if entry.get("short_title"):
            st = entry["short_title"].lower().strip()
            lookup[(author, st)] = entry

    # For authors with only one work, allow lookup by author alone
    for author, entries in by_author.items():
        if len(entries) == 1:
            lookup[(author, None)] = entries[0]

    return lookup


def _match_supra_to_work(
    author_text: str,
    short_title: str | None,
    lookup: dict[tuple[str, str | None], dict],
) -> dict | None:
    """Find the registry work matching a supra reference."""
    author_norm = author_text.lower().strip().rstrip(",. ")

    # Try with short title first
    if short_title:
        st_norm = short_title.lower().strip()
        match = lookup.get((author_norm, st_norm))
        if match:
            return match

    # Try author-only
    match = lookup.get((author_norm, None))
    if match:
        return match

    # Fuzzy: try substring matching on author
    for (a, _st), entry in lookup.items():
        if author_norm in a or a in author_norm:
            if short_title is None or _st is None:
                return entry
            if short_title and _st and short_title.lower().strip() in _st:
                return entry

    return None


def reverse_short_forms(tex: str, registry: dict) -> str:
    """Replace all supra/Id. references with full citations from the registry.

    Also strips [hereinafter ...] insertions since short_form.py will
    re-insert them.
    """
    lookup = _build_lookup(registry)
    footnotes = extract_footnotes(tex)

    if not footnotes:
        return tex

    # Build identity tracking for Id. reversal:
    # We need to know what the previous footnote cited to reverse Id.
    # Walk footnotes in order, reversing supra first, then Id.

    # Pass 1: reverse supra references and track identity per footnote
    subs: list[tuple[int, int, str]] = []
    fn_identities: dict[int, str | None] = {}  # fn_number -> identity_key of cited work

    for fn in footnotes:
        content = fn.content.strip()

        # Check for Id. — handle in pass 2
        if ID_PATTERN.match(content):
            fn_identities[fn.number] = "__ID__"
            continue

        # Check for supra references in this footnote
        parts = _split_at_semicolons(content)
        any_change = False
        new_parts = []
        last_identity = None

        for part in parts:
            m = SUPRA_PATTERN.search(part)
            if m:
                author_text = m.group(1)
                short_title = m.group(2)  # May be None
                work = _match_supra_to_work(author_text, short_title, lookup)
                if work and work.get("full_citation_text"):
                    # Extract the signal from the original supra reference
                    pre_author = part[:m.start()].strip()
                    full_text = work["full_citation_text"]
                    if pre_author:
                        # Signal was captured — re-apply it to the full citation
                        # Strip existing signal from full citation if present
                        full_stripped = _strip_leading_signal(full_text)
                        new_parts.append(f"{pre_author} {full_stripped}")
                    else:
                        new_parts.append(full_text)
                    any_change = True
                    last_identity = _identity_from_work(work)
                    continue
            # No supra match — keep as-is but try to identify the work
            new_parts.append(part)
            parse_result = _try_identify_part(part, registry)
            if parse_result:
                last_identity = parse_result

        if last_identity and last_identity != "__ID__":
            fn_identities[fn.number] = last_identity
        elif not any_change:
            # Try to identify the work from full citation text
            parse_result = _try_identify_content(content, registry)
            fn_identities[fn.number] = parse_result

        if any_change:
            new_content = "; ".join(new_parts)
            marker_prefix = f"{MARKER}\n" if fn.has_marker else ""
            new_fn = f"\\footnote{{{marker_prefix}{new_content}}}"
            subs.append((fn.start, fn.end, new_fn))

    # Apply supra substitutions
    subs.sort(key=lambda x: x[0], reverse=True)
    for start, end, replacement in subs:
        tex = tex[:start] + replacement + tex[end:]

    # Pass 2: reverse Id. references
    # Re-parse footnotes after supra changes
    footnotes = extract_footnotes(tex)
    id_subs: list[tuple[int, int, str]] = []

    prev_identity: str | None = None
    for fn in footnotes:
        content = fn.content.strip()
        if ID_PATTERN.match(content):
            # Find what the previous footnote cited
            if prev_identity and prev_identity != "__ID__":
                # Look up the full citation from registry
                work = _find_work_by_identity(prev_identity, registry)
                if work and work.get("full_citation_text"):
                    full_text = work["full_citation_text"]
                    marker_prefix = f"{MARKER}\n" if fn.has_marker else ""
                    new_fn = f"\\footnote{{{marker_prefix}{full_text}}}"
                    id_subs.append((fn.start, fn.end, new_fn))
                    # This footnote now cites the same work
                    # prev_identity stays the same
                    continue
            # Could not reverse — leave as-is
            # prev_identity stays the same (Id. refers to same work)
        else:
            prev_identity = _try_identify_content(content, registry)

    # Apply Id. substitutions
    id_subs.sort(key=lambda x: x[0], reverse=True)
    for start, end, replacement in id_subs:
        tex = tex[:start] + replacement + tex[end:]

    # Pass 3: strip [hereinafter \textit{...}] insertions
    tex = HEREINAFTER_PATTERN.sub("", tex)

    return tex


def _split_at_semicolons(content: str) -> list[str]:
    """Split footnote content at top-level semicolons."""
    parts = []
    depth = 0
    current: list[str] = []
    for ch in content:
        if ch == "{":
            depth += 1
            current.append(ch)
        elif ch == "}":
            depth -= 1
            current.append(ch)
        elif ch == ";" and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    remainder = "".join(current).strip()
    if remainder:
        parts.append(remainder)
    return parts


def _strip_leading_signal(text: str) -> str:
    """Strip a leading Bluebook signal from citation text."""
    signals = [
        "See generally", "See also", "But see", "But cf.",
        "Compare", "Cf.", "See", "E.g.,", "Accord",
    ]
    for sig in signals:
        pat = re.compile(r"^" + re.escape(sig) + r"\s+", re.IGNORECASE)
        if pat.match(text):
            return text[pat.match(text).end():]
    return text


def _identity_from_work(work: dict) -> str:
    """Reconstruct identity_key from a registry work entry."""
    author = work["author_key"].lower()
    title = re.sub(r"\s+", " ", work["title"]).strip().lower()
    title = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", title)
    title = re.sub(r"[{}\\]", "", title)
    return f"{author}|{title}"


def _try_identify_part(text: str, registry: dict) -> str | None:
    """Try to match a citation part to a registry work by author+title."""
    for identity_key, work in registry.get("works", {}).items():
        full = work.get("full_citation_text", "")
        if not full:
            continue
        # Check if the author_key appears in the text
        if work["author_key"] in text:
            # Check title presence (first 30 chars)
            title_snippet = work["title"][:30]
            if title_snippet.lower() in text.lower():
                return identity_key
    return None


def _try_identify_content(content: str, registry: dict) -> str | None:
    """Try to identify which work a full citation in a footnote refers to."""
    for identity_key, work in registry.get("works", {}).items():
        full = work.get("full_citation_text", "")
        if not full:
            continue
        # Check if the full citation text appears (fuzzy: first 50 chars)
        snippet = full[:50]
        if snippet in content:
            return identity_key
        # Check author + title combo
        if work["author_key"] in content:
            title_snippet = work["title"][:30]
            if title_snippet.lower() in content.lower():
                return identity_key
    return None


def _find_work_by_identity(identity_key: str, registry: dict) -> dict | None:
    """Find a work entry by its identity_key."""
    return registry.get("works", {}).get(identity_key)


# ── Main ─────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Reorder cross-references (supra/Id./hereinafter) after "
        "manual footnotes have been added"
    )
    parser.add_argument("--input", required=True, help="Input .tex file")
    parser.add_argument(
        "--plan-dir",
        default=None,
        help="Path to placement/ directory containing footnote_registry.json "
        "(default: placement/ alongside input .tex)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Resolve plan directory
    if args.plan_dir:
        plan_dir = Path(args.plan_dir)
    else:
        plan_dir = input_path.parent / "placement"

    if not plan_dir.is_dir():
        print(f"Error: Placement directory not found: {plan_dir}", file=sys.stderr)
        sys.exit(1)

    print("Reordering cross-references")
    print(f"  Input: {input_path}")
    print(f"  Registry: {plan_dir / 'footnote_registry.json'}")

    # Load registry
    registry = load_registry(plan_dir)
    work_count = len(registry.get("works", {}))
    print(f"  Works in registry: {work_count}")

    # Step 1: Reverse all supra/Id./hereinafter back to full citations
    tex = input_path.read_text(encoding="utf-8")

    # Count short forms before reversal
    supra_before = len(re.findall(r"\\textit\{supra\}", tex))
    id_before = len(re.findall(r"\\textit\{Id\.\}", tex))

    tex_restored = reverse_short_forms(tex, registry)

    # Count remaining short forms (should be zero if all reversed)
    supra_after = len(re.findall(r"\\textit\{supra\}", tex_restored))
    id_after = len(re.findall(r"\\textit\{Id\.\}", tex_restored))

    print(f"  Reversed: {supra_before - supra_after} supra, "
          f"{id_before - id_after} Id.")
    if supra_after > 0:
        print(f"  Warning: {supra_after} supra references could not be reversed")
    if id_after > 0:
        print(f"  Warning: {id_after} Id. references could not be reversed")

    # Step 2: Write restored .tex, then re-run short_form to apply
    # correct cross-references with updated footnote numbering
    input_path.write_text(tex_restored, encoding="utf-8")
    print("  Full citations restored. Re-running short-form processing...")

    short_form_process(
        str(input_path), str(input_path), str(plan_dir)
    )

    print("Cross-reference reordering complete.")


if __name__ == "__main__":
    main()
