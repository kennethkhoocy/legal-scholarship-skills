#!/usr/bin/env python3
"""
Ingest a citation spreadsheet (.xlsx) into citations.json and references_new.bib.

Deterministic script -- no LLM involvement. Uses openpyxl + standard library only.
Produces BibTeX entries with proper entry type mapping (article, book,
incollection, techreport, unpublished).

Usage:
    python ingest_citations.py \
        --input citations.xlsx \
        --output-json citations.json \
        --output-bib references_new.bib \
        --existing-bib references.bib \
        --min-score 0
"""

import argparse
import json
import re
import unicodedata
from pathlib import Path

try:
    import openpyxl
except ImportError:
    raise SystemExit(
        "openpyxl is required: pip install openpyxl"
    )


# ---------------------------------------------------------------------------
# Author name parsing
# ---------------------------------------------------------------------------

def _strip_accents(s: str) -> str:
    """Remove diacritics/accents from a string."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _parse_single_author(name: str) -> tuple[str, str]:
    """Return (last, first) from a single author string.

    Handles:
        "Last, First"
        "First Last"
        "First Middle Last"
    """
    name = name.strip()
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        return parts[0], parts[1] if len(parts) > 1 else ""
    parts = name.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], " ".join(parts[:-1])


def parse_authors(raw: str) -> list[tuple[str, str]]:
    """Parse an author string into a list of (last, first) tuples.

    Supports:
        "First Last, First Last, First Last"   (comma-separated full names)
        "Last, First and Last, First"           (BibTeX-style)
        "First Last and First Last"             (and-separated)
        "First Last; First Last"                (semicolon-separated)
    """
    if not raw or not raw.strip():
        return []

    raw = raw.strip()

    # If the string contains " and " -- split on that first
    if " and " in raw:
        segments = [s.strip() for s in raw.split(" and ")]
        authors = []
        for seg in segments:
            authors.append(_parse_single_author(seg))
        return authors

    # Semicolon-separated
    if ";" in raw:
        segments = [s.strip() for s in raw.split(";")]
        return [_parse_single_author(s) for s in segments if s]

    # Comma-separated -- need to distinguish "Last, First" from "Name1, Name2"
    parts = [p.strip() for p in raw.split(",")]

    if len(parts) == 2:
        # Could be "Last, First" (one author) or "First Last, First Last" (two)
        if " " not in parts[0] and " " not in parts[1]:
            return [(parts[0], parts[1])]
        return [_parse_single_author(p) for p in parts]

    if len(parts) > 2:
        return [_parse_single_author(p) for p in parts if p]

    # Single name, no commas
    return [_parse_single_author(raw)]


def authors_to_bibtex(authors: list[tuple[str, str]]) -> str:
    """Format author list as BibTeX `author` field value."""
    formatted = []
    for last, first in authors:
        if first:
            formatted.append(f"{last}, {first}")
        else:
            formatted.append(last)
    return " and ".join(formatted)


# ---------------------------------------------------------------------------
# Cite key generation
# ---------------------------------------------------------------------------

def _make_base_key(authors: list[tuple[str, str]], year: str, title: str) -> str:
    """Generate a Google-Scholar-style cite key: lastnameYEARfirstword."""
    if authors:
        last = _strip_accents(authors[0][0]).lower()
        last = re.sub(r"[^a-z]", "", last)
    else:
        last = "unknown"

    year_str = str(year).strip() if year else "nd"

    # First significant word of the title (skip articles)
    skip = {"a", "an", "the", "on", "of", "in", "for", "to", "and", "with"}
    words = re.findall(r"[a-zA-Z]+", title or "")
    first_word = ""
    for w in words:
        if w.lower() not in skip:
            first_word = w.lower()
            break
    if not first_word and words:
        first_word = words[0].lower()

    return f"{last}{year_str}{first_word}"


def generate_cite_key(
    authors: list[tuple[str, str]],
    year: str,
    title: str,
    existing_keys: set[str],
) -> str:
    """Generate a unique cite key, appending b/c/... on collision."""
    base = _make_base_key(authors, year, title)
    if not base:
        base = "ref"
    key = base
    if key not in existing_keys:
        return key
    for suffix in "bcdefghijklmnopqrstuvwxyz":
        candidate = f"{base}{suffix}"
        if candidate not in existing_keys:
            return candidate
    # Extremely unlikely fallback
    import random
    return f"{base}{random.randint(100, 999)}"


# ---------------------------------------------------------------------------
# Existing .bib parsing (lightweight)
# ---------------------------------------------------------------------------

def _normalize_doi(doi: str) -> str:
    """Normalize a DOI for comparison: lowercase, strip URL prefixes."""
    doi = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi


def parse_existing_bib(bib_path: Path) -> tuple[set[str], dict[str, str]]:
    """Parse a .bib file and return (keys, doi_map).

    doi_map: normalized_doi -> cite_key
    """
    keys: set[str] = set()
    doi_map: dict[str, str] = {}

    text = bib_path.read_text(encoding="utf-8", errors="replace")

    entry_pattern = re.compile(r"@\w+\{([^,]+),", re.IGNORECASE)
    for m in entry_pattern.finditer(text):
        keys.add(m.group(1).strip())

    doi_pattern = re.compile(r"doi\s*=\s*\{([^}]+)\}", re.IGNORECASE)
    entries = re.split(r"(?=@\w+\{)", text)
    for entry in entries:
        key_match = entry_pattern.search(entry)
        if not key_match:
            continue
        key = key_match.group(1).strip()
        doi_match = doi_pattern.search(entry)
        if doi_match:
            doi_map[_normalize_doi(doi_match.group(1))] = key

    return keys, doi_map


# ---------------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------------

# Known columns mapped to JSON field names
KNOWN_COLUMNS = {
    "title": "title",
    "authors": "authors",
    "author": "authors",
    "year": "year",
    "journal": "journal",
    "doi": "doi",
    "abstract": "abstract",
    "relationship": "relationship",
    "screening_rationale": "screening_rationale",
    "screening_score": "screening_score",
    "paper_type": "paper_type",
    "identification_strategy": "identification_strategy",
    "source": "source",
    "url": "url",
    "publisher": "publisher",
    "booktitle": "booktitle",
}


def detect_columns(headers: list[str]) -> dict[int, str]:
    """Map column index -> JSON field name.

    Returns a dict mapping each column index to its standardized field name.
    Unrecognized columns are kept as-is (pass-through).
    """
    mapping: dict[int, str] = {}
    relevance_col_idx: int | None = None
    relevance_col_priority: int = 999  # lower = better

    for i, raw_header in enumerate(headers):
        if raw_header is None:
            continue
        header = str(raw_header).strip()
        header_lower = header.lower()

        # Check known columns (exact match on lowercased)
        if header_lower in KNOWN_COLUMNS:
            mapping[i] = KNOWN_COLUMNS[header_lower]
            continue

        # Relevance column detection
        if header_lower == "relevance":
            if relevance_col_priority > 1:
                relevance_col_idx = i
                relevance_col_priority = 1
        elif "relevance" in header_lower:
            if relevance_col_priority > 2:
                relevance_col_idx = i
                relevance_col_priority = 2

        # If not matched, keep original header as field name (pass-through)
        if i not in mapping and relevance_col_idx != i:
            mapping[i] = header

    if relevance_col_idx is not None:
        mapping[relevance_col_idx] = "relevance_note"

    return mapping


# ---------------------------------------------------------------------------
# BibTeX entry type detection
# ---------------------------------------------------------------------------

_WORKING_PAPER_PATTERNS = re.compile(
    r"(working\s+paper|ssrn|nber|cepr|iza|ecb\s+working|imf\s+working"
    r"|world\s+bank\s+policy|discussion\s+paper|staff\s+report)",
    re.IGNORECASE,
)


def _detect_entry_type(record: dict) -> str:
    """Determine the BibTeX entry type from available metadata."""
    journal = str(record.get("journal", "") or "").strip()
    publisher = str(record.get("publisher", "") or "").strip()
    booktitle = str(record.get("booktitle", "") or "").strip()
    source = str(record.get("source", "") or "").strip()
    paper_type = str(record.get("paper_type", "") or "").strip()

    # Check for working paper indicators in various fields
    text_to_check = f"{journal} {source} {paper_type}"
    if _WORKING_PAPER_PATTERNS.search(text_to_check):
        return "techreport"

    if journal:
        return "article"

    if booktitle:
        return "incollection"

    if publisher:
        return "book"

    return "unpublished"


# ---------------------------------------------------------------------------
# BibTeX entry generation
# ---------------------------------------------------------------------------

def _escape_bibtex(value: str) -> str:
    """Escape special characters for BibTeX field values."""
    value = re.sub(r"(?<!\\)&", r"\\&", value)
    return value


def make_bib_entry(record: dict, cite_key: str) -> str:
    """Generate a BibTeX entry string from a citation record."""
    entry_type = _detect_entry_type(record)

    lines = [f"@{entry_type}{{{cite_key},"]

    # Title
    if record.get("title"):
        lines.append(f"  title = {{{_escape_bibtex(str(record['title']))}}},")

    # Author
    if record.get("authors"):
        authors = parse_authors(str(record["authors"]))
        lines.append(f"  author = {{{authors_to_bibtex(authors)}}},")

    # Year
    if record.get("year"):
        lines.append(f"  year = {{{record['year']}}},")

    # Type-specific fields
    journal = str(record.get("journal", "") or "").strip()
    publisher = str(record.get("publisher", "") or "").strip()
    booktitle = str(record.get("booktitle", "") or "").strip()

    if entry_type == "article" and journal:
        lines.append(f"  journal = {{{_escape_bibtex(journal)}}},")

    if entry_type == "book" and publisher:
        lines.append(f"  publisher = {{{_escape_bibtex(publisher)}}},")

    if entry_type == "incollection":
        if booktitle:
            lines.append(f"  booktitle = {{{_escape_bibtex(booktitle)}}},")
        if publisher:
            lines.append(f"  publisher = {{{_escape_bibtex(publisher)}}},")

    if entry_type == "techreport":
        # Use journal field as institution if it looks like a working paper series
        institution = journal or "Working Paper"
        lines.append(f"  institution = {{{_escape_bibtex(institution)}}},")

    if entry_type == "unpublished":
        lines.append(f"  note = {{Working paper}},")

    # DOI (all types)
    if record.get("doi"):
        lines.append(f"  doi = {{{record['doi']}}},")

    # URL (if present and no DOI)
    if record.get("url") and not record.get("doi"):
        lines.append(f"  url = {{{record['url']}}},")

    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main ingestion logic
# ---------------------------------------------------------------------------

def ingest(
    input_path: Path,
    output_json: Path,
    output_bib: Path,
    existing_bib: Path | None = None,
    min_score: float = 0,
) -> None:
    """Run the full ingestion pipeline."""

    # Load existing .bib for duplicate detection
    existing_keys: set[str] = set()
    existing_dois: dict[str, str] = {}

    if existing_bib and existing_bib.exists():
        existing_keys, existing_dois = parse_existing_bib(existing_bib)
        print(f"Loaded existing .bib: {len(existing_keys)} entries")

    # Read the xlsx
    wb = openpyxl.load_workbook(input_path, read_only=True, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise SystemExit("Error: spreadsheet is empty")

    headers = [str(h) if h is not None else None for h in rows[0]]
    col_map = detect_columns(headers)

    has_relevance = "relevance_note" in col_map.values()
    print(f"Detected columns: {json.dumps({headers[i]: v for i, v in col_map.items()}, indent=2)}")

    # Process rows
    citations: list[dict] = []
    bib_entries: list[str] = []
    all_keys: set[str] = set(existing_keys)
    n_duplicates = 0
    n_skipped_score = 0

    # Count entry types for summary
    type_counts: dict[str, int] = {}

    for row_idx, row in enumerate(rows[1:], start=2):
        record: dict = {}
        for col_idx, field_name in col_map.items():
            if col_idx < len(row):
                val = row[col_idx]
                if val is not None:
                    record[field_name] = str(val).strip() if not isinstance(val, (int, float)) else val
                else:
                    record[field_name] = ""
            else:
                record[field_name] = ""

        # If no relevance column exists in the spreadsheet, set to None
        if not has_relevance:
            record["relevance_note"] = None

        # Skip rows without a title
        if not record.get("title"):
            continue

        # Filter by screening score
        score = record.get("screening_score", "")
        if score != "" and min_score > 0:
            try:
                if float(score) < min_score:
                    n_skipped_score += 1
                    continue
            except (ValueError, TypeError):
                pass

        # Parse authors for key generation
        authors = parse_authors(str(record.get("authors", "")))

        # Duplicate detection (DOI only -- upstream pipeline handles dedup)
        is_duplicate = False
        existing_match_key = None

        raw_doi = str(record.get("doi", "")).strip()
        if raw_doi:
            norm_doi = _normalize_doi(raw_doi)
            if norm_doi and norm_doi in existing_dois:
                is_duplicate = True
                existing_match_key = existing_dois[norm_doi]

        # Generate cite key
        year_str = str(record.get("year", "")).strip()
        cite_key = generate_cite_key(authors, year_str, str(record.get("title", "")), all_keys)
        all_keys.add(cite_key)

        record["cite_key"] = cite_key
        record["already_in_bib"] = is_duplicate
        if existing_match_key:
            record["existing_bib_key"] = existing_match_key

        # Detect and record entry type
        entry_type = _detect_entry_type(record)
        record["entry_type"] = entry_type
        type_counts[entry_type] = type_counts.get(entry_type, 0) + 1

        citations.append(record)

        if is_duplicate:
            n_duplicates += 1
        else:
            bib_entry = make_bib_entry(record, cite_key)
            bib_entries.append(bib_entry)

    wb.close()

    # Write outputs
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_bib.parent.mkdir(parents=True, exist_ok=True)

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(citations, f, indent=2, ensure_ascii=False, default=str)

    with open(output_bib, "w", encoding="utf-8") as f:
        f.write("% Auto-generated by ingest_citations.py\n")
        f.write("% Do not edit manually -- re-run the script to regenerate.\n\n")
        f.write("\n\n".join(bib_entries))
        f.write("\n")

    # Summary
    n_written = len(bib_entries)
    print(f"\n{'='*50}")
    print(f"Citation ingestion complete")
    print(f"  Total citations processed: {len(citations)}")
    print(f"  Duplicates found (in existing .bib): {n_duplicates}")
    print(f"  Skipped (below min score {min_score}): {n_skipped_score}")
    print(f"  New entries written to .bib: {n_written}")
    print(f"  Entry types: {json.dumps(type_counts)}")
    print(f"  Output JSON: {output_json}")
    print(f"  Output BIB:  {output_bib}")
    print(f"{'='*50}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Ingest citation spreadsheet into citations.json + .bib"
    )
    parser.add_argument(
        "--input", required=True, type=Path,
        help="Path to the .xlsx citation spreadsheet"
    )
    parser.add_argument(
        "--output-json", required=True, type=Path,
        help="Path for output citations.json"
    )
    parser.add_argument(
        "--output-bib", required=True, type=Path,
        help="Path for output references_new.bib"
    )
    parser.add_argument(
        "--existing-bib", type=Path, default=None,
        help="Path to existing .bib file for duplicate detection"
    )
    parser.add_argument(
        "--min-score", type=float, default=0,
        help="Minimum screening_score to include (default: 0 = no filtering)"
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Error: input file not found: {args.input}")

    if args.existing_bib and not args.existing_bib.exists():
        print(f"Warning: --existing-bib file not found: {args.existing_bib}")
        args.existing_bib = None

    ingest(
        input_path=args.input,
        output_json=args.output_json,
        output_bib=args.output_bib,
        existing_bib=args.existing_bib,
        min_score=args.min_score,
    )


if __name__ == "__main__":
    main()
