#!/usr/bin/env python3
"""
Phase 1.5: Verify existing citations against the .bib file and external APIs
(OpenAlex, CrossRef, optionally Google Scholar via SearchAPI).

Unified verifier for both cite-placement modes:

  inline    -- verify \\cite{key} bib entries, flag dangling references and
               hallucinated bib entries, and detect overlaps with an RA
               spreadsheet.
  footnotes -- verify extracted footnote citations, check Bluebook formatting,
               and detect overlaps with an RA spreadsheet.

Usage:
    python scripts/core/verify_citations.py --mode inline \\
        --citations placement/existing_citations.json \\
        --bib references.bib \\
        --output placement/audit_report.json \\
        [--spreadsheet citations.xlsx]

    python scripts/core/verify_citations.py --mode footnotes \\
        --footnotes placement/existing_footnotes.json \\
        --output placement/audit_report.json \\
        [--spreadsheet citations.xlsx]
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# -- Matching helpers ---------------------------------------------------------

STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "for", "and", "or", "to",
    "from", "with", "by", "at", "is", "are", "was", "were", "its",
}


def word_set(text: str) -> set[str]:
    """Lowercase word set excluding stopwords and short tokens."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def author_match(extracted: str, candidates: list[str]) -> bool:
    """Check if any candidate author list contains the extracted last name."""
    if not extracted:
        return False
    extracted_last = extracted.strip().split()[-1].lower() if extracted.strip() else ""
    if not extracted_last:
        return False
    for name in candidates:
        if extracted_last in name.lower():
            return True
    return False


# -- Bib parsing --------------------------------------------------------------

def _normalize_doi(doi: str) -> str:
    """Normalize a DOI for comparison."""
    doi = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi


def parse_bib_file(bib_path: Path) -> dict[str, dict]:
    """Parse a .bib file into a dict of cite_key -> metadata."""
    text = bib_path.read_text(encoding="utf-8", errors="replace")
    entries: dict[str, dict] = {}

    entry_pattern = re.compile(r"@(\w+)\{([^,]+),", re.IGNORECASE)
    field_pattern = re.compile(r"(\w+)\s*=\s*\{([^}]*)\}", re.IGNORECASE)

    raw_entries = re.split(r"(?=@\w+\{)", text)
    for raw in raw_entries:
        key_match = entry_pattern.search(raw)
        if not key_match:
            continue
        entry_type = key_match.group(1).lower()
        cite_key = key_match.group(2).strip()

        fields = {}
        for fm in field_pattern.finditer(raw):
            fields[fm.group(1).lower()] = fm.group(2).strip()

        entries[cite_key] = {
            "entry_type": entry_type,
            "title": fields.get("title", ""),
            "author": fields.get("author", ""),
            "year": fields.get("year", ""),
            "journal": fields.get("journal", ""),
            "doi": fields.get("doi", ""),
        }

    return entries


# -- API clients --------------------------------------------------------------

HEADERS = {"User-Agent": "cite-placement/1.0 (mailto:research@example.com)"}


def _get_json(url: str, timeout: int = 15) -> dict | None:
    """Fetch JSON from URL, return parsed dict or None on failure."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def search_openalex(title: str) -> dict | None:
    """Search OpenAlex for a title. Returns best result metadata or None."""
    encoded = urllib.parse.quote(title[:200])
    url = f"https://api.openalex.org/works?search={encoded}&per_page=3"
    data = _get_json(url)
    if not data or "results" not in data or not data["results"]:
        return None

    for result in data["results"]:
        r_title = result.get("title", "")
        r_year = result.get("publication_year")
        r_authors = []
        for authorship in result.get("authorships", []):
            author = authorship.get("author", {})
            name = author.get("display_name", "")
            if name:
                r_authors.append(name)
        r_doi = result.get("doi", "")
        r_journal = ""
        loc = result.get("primary_location", {})
        if loc:
            source = loc.get("source", {})
            if source:
                r_journal = source.get("display_name", "")
        r_volume = ""
        r_pages = ""
        biblio = result.get("biblio", {})
        if biblio:
            r_volume = biblio.get("volume", "") or ""
            first = biblio.get("first_page", "") or ""
            last = biblio.get("last_page", "") or ""
            r_pages = f"{first}-{last}" if first and last else first

        return {
            "title": r_title,
            "authors": r_authors,
            "year": r_year,
            "journal": r_journal,
            "doi": r_doi.replace("https://doi.org/", "") if r_doi else "",
            "volume": r_volume,
            "pages": r_pages,
            "source": "openalex",
        }
    return None


def search_crossref(title: str) -> dict | None:
    """Search CrossRef for a title. Returns best result metadata or None."""
    encoded = urllib.parse.quote(title[:200])
    url = f"https://api.crossref.org/works?query.title={encoded}&rows=3"
    time.sleep(1)  # Polite rate limit
    data = _get_json(url)
    if not data or "message" not in data:
        return None
    items = data["message"].get("items", [])
    if not items:
        return None

    result = items[0]
    r_title_parts = result.get("title", [])
    r_title = r_title_parts[0] if r_title_parts else ""
    date_parts = result.get("published-print", {}).get("date-parts", [[None]])
    if not date_parts or not date_parts[0]:
        date_parts = result.get("published-online", {}).get("date-parts", [[None]])
    r_year = date_parts[0][0] if date_parts and date_parts[0] else None
    r_authors = []
    for a in result.get("author", []):
        given = a.get("given", "")
        family = a.get("family", "")
        r_authors.append(f"{given} {family}".strip())
    r_doi = result.get("DOI", "")
    r_journal_parts = result.get("container-title", [])
    r_journal = r_journal_parts[0] if r_journal_parts else ""
    r_volume = result.get("volume", "") or ""
    r_pages = result.get("page", "") or ""

    return {
        "title": r_title,
        "authors": r_authors,
        "year": r_year,
        "journal": r_journal,
        "doi": r_doi,
        "volume": r_volume,
        "pages": r_pages,
        "source": "crossref",
    }


def search_google_scholar(title: str, api_key: str) -> dict | None:
    """Search Google Scholar via SearchAPI. Returns best result or None."""
    encoded = urllib.parse.quote(title[:200])
    url = f"https://www.searchapi.io/api/v1/search?engine=google_scholar&q={encoded}&api_key={api_key}"
    data = _get_json(url)
    if not data:
        return None
    results = data.get("organic_results", [])
    if not results:
        return None

    result = results[0]
    r_title = result.get("title", "")
    r_year = None
    # Try to extract year from publication_info
    pub_info = result.get("publication_info", {}).get("summary", "")
    year_match = re.search(r"\b(19|20)\d{2}\b", pub_info)
    if year_match:
        r_year = int(year_match.group())
    r_authors = []
    for a in result.get("publication_info", {}).get("authors", []):
        r_authors.append(a.get("name", ""))

    return {
        "title": r_title,
        "authors": r_authors,
        "year": r_year,
        "journal": "",
        "doi": "",
        "volume": "",
        "pages": "",
        "source": "google_scholar",
    }


# -- Verification logic -------------------------------------------------------

# field_map presets: logical field name -> entry key name.
INLINE_FIELD_MAP = {"title": "title", "author": "author", "year": "year"}
FOOTNOTES_FIELD_MAP = {
    "title": "extracted_title",
    "author": "extracted_author",
    "year": "extracted_year",
}


def verify_one(
    entry: dict,
    searchapi_key: str | None,
    *,
    field_map: dict[str, str],
    capture_metadata: bool,
    em_dash: bool = False,
) -> dict:
    """Verify a single citation/bib entry against external APIs.

    ``field_map`` maps the logical fields ``title``/``author``/``year`` onto the
    actual key names used by the entry (inline bib entries vs. extracted
    footnote entries). When ``capture_metadata`` is True the full matched
    metadata dict is stored under ``verified_metadata`` (footnotes behaviour).
    ``em_dash`` selects the punctuation used in the human-readable ``note``
    string so each mode reproduces its original report text exactly.
    """
    title = entry.get(field_map["title"], "")
    author = entry.get(field_map["author"], "")
    year_raw = entry.get(field_map["year"])
    year = None
    if isinstance(year_raw, int):
        year = year_raw
    elif year_raw:
        try:
            # Intentional merge change: footnotes mode now int-coerces string
            # years too (source used the raw value); more robust, same matches.
            year = int(year_raw)
        except (ValueError, TypeError):
            year = None

    title_words = word_set(title)
    result = dict(entry)
    best_match = None
    best_jaccard = 0.0

    # 1. OpenAlex
    oa = search_openalex(title)
    if oa:
        j = jaccard(title_words, word_set(oa["title"]))
        year_ok = oa["year"] is not None and year is not None and abs(oa["year"] - year) <= 1
        auth_ok = author_match(author, oa["authors"])
        if j > best_jaccard:
            best_jaccard = j
            best_match = oa
        if j > 0.85 and year_ok and auth_ok:
            result["status"] = "verified"
            result["verified_via"] = "openalex"
            result["verified_doi"] = oa["doi"]
            if capture_metadata:
                result["verified_metadata"] = oa
            return result

    # 2. CrossRef
    cr = search_crossref(title)
    if cr:
        j = jaccard(title_words, word_set(cr["title"]))
        year_ok = cr["year"] is not None and year is not None and abs(cr["year"] - year) <= 1
        auth_ok = author_match(author, cr["authors"])
        if j > best_jaccard:
            best_jaccard = j
            best_match = cr
        if j > 0.85 and year_ok and auth_ok:
            result["status"] = "verified"
            result["verified_via"] = "crossref"
            result["verified_doi"] = cr["doi"]
            if capture_metadata:
                result["verified_metadata"] = cr
            return result

    # 3. Google Scholar (optional)
    if searchapi_key:
        gs = search_google_scholar(title, searchapi_key)
        if gs:
            j = jaccard(title_words, word_set(gs["title"]))
            year_ok = gs["year"] is not None and year is not None and abs(gs["year"] - year) <= 1
            auth_ok = author_match(author, gs["authors"]) if gs["authors"] else True
            if j > best_jaccard:
                best_jaccard = j
                best_match = gs
            if j > 0.85 and (year_ok or gs["year"] is None) and auth_ok:
                result["status"] = "verified"
                result["verified_via"] = "google_scholar"
                result["verified_doi"] = gs.get("doi", "")
                if capture_metadata:
                    result["verified_metadata"] = gs
                return result

    # Classify as hallucinated or unverified
    dash = "—" if em_dash else "--"
    if best_match and best_jaccard < 0.5:
        result["status"] = "hallucinated"
        result["note"] = (
            f"No matching paper found. Best candidate (Jaccard={best_jaccard:.2f}): "
            f"'{best_match['title']}'"
        )
    else:
        result["status"] = "unverified"
        if best_match:
            result["note"] = (
                f"Ambiguous match (Jaccard={best_jaccard:.2f}): "
                f"'{best_match['title']}' {dash} manual review recommended"
            )
        else:
            result["note"] = f"No results from any API {dash} manual review recommended"

    return result


# -- Overlap detection ---------------------------------------------------------

def load_spreadsheet_for_overlap(xlsx_path: str) -> list[dict]:
    """Load spreadsheet titles, DOIs, and cite keys for overlap checking."""
    try:
        import openpyxl
    except ImportError:
        print("  Warning: openpyxl not installed, skipping spreadsheet overlap detection")
        return []

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [str(h).strip().lower() if h else "" for h in rows[0]]
    entries = []
    for row in rows[1:]:
        d = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
        title = str(d.get("title", "") or "")
        doi = str(d.get("doi", "") or "").strip()
        cite_key = str(d.get("cite_key", "") or "")
        if title:
            entries.append({"title": title, "doi": doi, "cite_key": cite_key})
    wb.close()
    return entries


def _find_overlap(
    my_doi: str,
    my_title_words: set[str],
    spreadsheet: list[dict],
    normalize_doi,
) -> dict | None:
    """Shared overlap scan: DOI equality then title Jaccard > 0.85."""
    for entry in spreadsheet:
        s_doi = normalize_doi(entry["doi"])
        if my_doi and s_doi and my_doi == s_doi:
            return entry
        s_title_words = word_set(entry["title"])
        if jaccard(my_title_words, s_title_words) > 0.85:
            return entry
    return None


def check_overlap_inline(bib_entry: dict, spreadsheet: list[dict]) -> dict | None:
    """Check if a bib entry overlaps with a spreadsheet entry (inline mode)."""
    my_doi = _normalize_doi(bib_entry.get("doi", ""))
    my_title_words = word_set(bib_entry.get("title", ""))
    return _find_overlap(my_doi, my_title_words, spreadsheet, _normalize_doi)


def check_overlap_footnotes(citation: dict, spreadsheet: list[dict]) -> dict | None:
    """Check if a verified citation overlaps with a spreadsheet entry (footnotes)."""

    def _norm(s: str) -> str:
        s = s.strip().lower()
        return re.sub(r"^https?://doi\.org/", "", s)

    my_doi = _norm(citation.get("verified_doi", ""))
    my_title_words = word_set(citation.get("extracted_title", ""))
    return _find_overlap(my_doi, my_title_words, spreadsheet, _norm)


# -- Bluebook format checking (footnotes mode) --------------------------------

BLUEBOOK_JOURNAL_ABBREVS = {
    "stanford law review": "Stan. L. Rev.",
    "yale law journal": "Yale L.J.",
    "harvard law review": "Harv. L. Rev.",
    "journal of financial economics": "J. Fin. Econ.",
    "journal of finance": "J. Fin.",
    "review of financial studies": "Rev. Fin. Stud.",
    "american economic review": "Am. Econ. Rev.",
    "quarterly journal of economics": "Q.J. Econ.",
    "journal of law and economics": "J.L. & Econ.",
    "journal of legal studies": "J. Legal Stud.",
    "journal of corporate finance": "J. Corp. Fin.",
    "journal of comparative economics": "J. Comp. Econ.",
    "journal of management": "J. Mgmt.",
    "strategic management journal": "Strategic Mgmt. J.",
    "delaware journal of corporate law": "Del. J. Corp. L.",
    "yale journal on regulation": "Yale J. on Reg.",
    "american journal of comparative law": "Am. J. Comp. L.",
    "journal of economic literature": "J. Econ. Lit.",
}


def check_bluebook_format(citation: dict) -> tuple[list[str], str]:
    """Check Bluebook formatting issues. Returns (issues, corrected_string)."""
    issues = []
    meta = citation.get("verified_metadata", {})
    if not meta:
        return issues, ""

    raw = citation.get("raw_text", "")
    journal_full = meta.get("journal", "")
    journal_lower = journal_full.lower()

    # Check journal abbreviation
    if journal_full and journal_lower in BLUEBOOK_JOURNAL_ABBREVS:
        expected_abbrev = BLUEBOOK_JOURNAL_ABBREVS[journal_lower]
        if expected_abbrev not in raw and journal_full in raw:
            issues.append(
                f"journal should be '{expected_abbrev}' not '{journal_full}'"
            )

    # Check title italics
    title = meta.get("title", "")
    if title and r"\textit{" not in raw and title[:20] in raw:
        issues.append("article title should be in \\textit{}")

    # Check volume/page
    volume = meta.get("volume", "")
    if volume and volume not in raw:
        issues.append(f"missing or incorrect volume number (should be {volume})")

    pages = meta.get("pages", "")
    first_page = pages.split("-")[0].strip() if pages else ""
    if first_page and first_page not in raw:
        issues.append(f"missing or incorrect page number (should start at {first_page})")

    # Build corrected Bluebook string
    authors = meta.get("authors", [])
    if len(authors) == 1:
        author_str = authors[0]
    elif len(authors) == 2:
        author_str = f"{authors[0]} \\& {authors[1]}"
    elif len(authors) >= 3:
        author_str = f"{authors[0]} et al."
    else:
        author_str = citation.get("extracted_author", "Unknown")

    # Determine journal abbreviation
    journal_abbrev = BLUEBOOK_JOURNAL_ABBREVS.get(journal_lower, journal_full)

    year = meta.get("year", citation.get("extracted_year", ""))
    vol_str = f"{volume} " if volume else ""
    page_str = f"\\ {first_page}" if first_page else ""

    if journal_full:
        corrected = (
            f"{author_str}, \\textit{{{title}}}, "
            f"{vol_str}\\textsc{{{journal_abbrev}}}{page_str} ({year})"
        )
    else:
        corrected = f"{author_str}, \\textit{{{title}}} ({year})"

    return issues, corrected


# -- Main processing: inline mode ---------------------------------------------

def process_inline(
    citations_path: str,
    bib_path: str,
    output_path: str,
    spreadsheet_path: str | None,
) -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    citations_data = json.loads(Path(citations_path).read_text(encoding="utf-8"))
    bib_entries = parse_bib_file(Path(bib_path))
    searchapi_key = os.environ.get("SEARCHAPI_API_KEY")

    print("Phase 1.5: Citation Audit (Inline)")
    print(f"  Cite commands in manuscript: {len(citations_data.get('citations', []))}")
    print(f"  Bib entries: {len(bib_entries)}")
    if searchapi_key:
        print("  Google Scholar: enabled (SEARCHAPI_API_KEY set)")
    else:
        print("  Google Scholar: disabled (SEARCHAPI_API_KEY not set)")

    # 1. Check for dangling references
    cite_keys_in_tex = {c["cite_key"] for c in citations_data.get("citations", [])}
    bib_keys = set(bib_entries.keys())
    dangling = cite_keys_in_tex - bib_keys

    if dangling:
        print(f"\n  [!] Dangling references ({len(dangling)} keys not in .bib):")
        for k in sorted(dangling):
            print(f"    - {k}")

    # 2. Verify bib entries
    spreadsheet = []
    if spreadsheet_path and Path(spreadsheet_path).is_file():
        spreadsheet = load_spreadsheet_for_overlap(spreadsheet_path)
        print(f"  Spreadsheet loaded: {len(spreadsheet)} entries for overlap detection")

    verified_results = []
    counts = {"verified": 0, "unverified": 0, "hallucinated": 0}
    verified_sources = {"openalex": 0, "crossref": 0, "google_scholar": 0}
    overlaps = []

    for i, (cite_key, entry) in enumerate(bib_entries.items()):
        title = entry.get("title", "?")[:60]
        print(f"  [{i + 1}/{len(bib_entries)}] Verifying: {title}...", end="")

        result = verify_one(
            entry,
            searchapi_key,
            field_map=INLINE_FIELD_MAP,
            capture_metadata=False,
            em_dash=False,
        )
        result["cite_key"] = cite_key
        counts[result["status"]] += 1

        if result["status"] == "verified":
            verified_sources[result["verified_via"]] += 1

        # Overlap check
        if result["status"] == "verified" and spreadsheet:
            overlap = check_overlap_inline(entry, spreadsheet)
            if overlap:
                overlaps.append({
                    "cite_key": cite_key,
                    "spreadsheet_title": overlap["title"],
                    "action": "update_metadata",
                })

        verified_results.append(result)
        print(f" {result['status']}")
        time.sleep(0.15)

    # Build report
    report = {
        "summary": {
            "total_cite_commands": len(cite_keys_in_tex),
            "unique_keys": len(cite_keys_in_tex),
            "dangling_references": len(dangling),
            "bib_entries_verified": counts["verified"],
            "bib_entries_unverified": counts["unverified"],
            "bib_entries_hallucinated": counts["hallucinated"],
            "overlaps_with_spreadsheet": len(overlaps),
            "verified_sources": verified_sources,
        },
        "dangling": [
            {"cite_key": k, "locations": []}
            for k in sorted(dangling)
        ],
        "bib_entries": verified_results,
        "overlaps": overlaps,
    }

    Path(output_path).write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Console summary
    print()
    print(f"  Dangling references: {len(dangling)}")
    v = counts["verified"]
    print(
        f"  Verified: {v} "
        f"(OpenAlex: {verified_sources['openalex']}, "
        f"CrossRef: {verified_sources['crossref']}, "
        f"Google Scholar: {verified_sources['google_scholar']})"
    )
    print(f"  Unverified: {counts['unverified']}")
    print(f"  Hallucinated: {counts['hallucinated']}")
    if overlaps:
        print(f"  Spreadsheet overlaps: {len(overlaps)}")

    hallucinated = [r for r in verified_results if r["status"] == "hallucinated"]
    if hallucinated:
        print()
        print("  [!] Hallucinated bib entries:")
        for h in hallucinated:
            print(f"    - {h['cite_key']}: \"{h.get('title', '?')[:60]}\"")

    print(f"\n  Audit report written to: {output_path}")


# -- Main processing: footnotes mode ------------------------------------------

def process_footnotes(
    footnotes_path: str,
    output_path: str,
    spreadsheet_path: str | None,
) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    _data = json.loads(Path(footnotes_path).read_text(encoding="utf-8"))
    # Accept the legacy bare array and the object form Phase 1 writes when
    # % CITE: slots are present ({"footnotes": [...], "citation_slots": [...]}).
    footnotes = _data["footnotes"] if isinstance(_data, dict) else _data
    searchapi_key = os.environ.get("SEARCHAPI_API_KEY")

    print("Phase 1.5: Citation Audit")
    print(f"  Citations to verify: {len(footnotes)}")
    if searchapi_key:
        print("  Google Scholar: enabled (SEARCHAPI_API_KEY set)")
    else:
        print("  Google Scholar: disabled (SEARCHAPI_API_KEY not set)")

    # Load spreadsheet for overlap
    spreadsheet = []
    if spreadsheet_path and Path(spreadsheet_path).is_file():
        spreadsheet = load_spreadsheet_for_overlap(spreadsheet_path)
        print(f"  Spreadsheet loaded: {len(spreadsheet)} entries for overlap detection")

    # Verify each citation
    results = []
    counts = {"verified": 0, "unverified": 0, "hallucinated": 0}
    verified_sources = {"openalex": 0, "crossref": 0, "google_scholar": 0}
    format_issue_count = 0
    overlap_count = 0

    for i, entry in enumerate(footnotes):
        print(f"  [{i + 1}/{len(footnotes)}] Verifying: {entry.get('extracted_title', '?')[:60]}...", end="")
        result = verify_one(
            entry,
            searchapi_key,
            field_map=FOOTNOTES_FIELD_MAP,
            capture_metadata=True,
            em_dash=True,
        )

        # Bluebook format check (only for verified)
        if result["status"] == "verified":
            issues, corrected = check_bluebook_format(result)
            if issues:
                result["format_issues"] = issues
                result["corrected_bluebook"] = corrected
                format_issue_count += 1
            verified_sources[result["verified_via"]] += 1

        # Overlap check (only for verified)
        if result["status"] == "verified" and spreadsheet:
            overlap = check_overlap_footnotes(result, spreadsheet)
            if overlap:
                result["overlaps_with_spreadsheet"] = True
                result["spreadsheet_cite_key"] = overlap.get("cite_key", "")
                overlap_count += 1
            else:
                result["overlaps_with_spreadsheet"] = False

        counts[result["status"]] += 1
        results.append(result)
        print(f" {result['status']}")

        # Rate limit between requests
        time.sleep(0.15)

    # Build audit report
    # Count footnote types from the input
    type_counts: dict[str, int] = {}
    for entry in footnotes:
        t = entry.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    report = {
        "summary": {
            "total_footnotes_audited": len(footnotes),
            "classified": type_counts,
            "verified": counts["verified"],
            "unverified": counts["unverified"],
            "hallucinated": counts["hallucinated"],
            "format_issues": format_issue_count,
            "overlaps_with_spreadsheet": overlap_count,
            "verified_sources": verified_sources,
        },
        "citations": results,
    }

    Path(output_path).write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Console summary
    print()
    print(f"  Total citations checked: {len(footnotes)}")
    v = counts["verified"]
    print(
        f"  Verified: {v} "
        f"(OpenAlex: {verified_sources['openalex']}, "
        f"CrossRef: {verified_sources['crossref']}, "
        f"Google Scholar: {verified_sources['google_scholar']})"
    )
    print(f"  Unverified: {counts['unverified']} (manual review recommended)")
    print(f"  Hallucinated: {counts['hallucinated']} (no matching publication found)")
    print(f"  Format issues: {format_issue_count} citations need Bluebook corrections")
    if spreadsheet:
        print(f"  Spreadsheet overlaps: {overlap_count}")

    # Flag hallucinated
    hallucinated = [r for r in results if r["status"] == "hallucinated"]
    if hallucinated:
        print()
        print("  [!] Hallucinated citations:")
        for h in hallucinated:
            fn = h.get("footnote_number", "?")
            title = h.get("extracted_title", "?")[:60]
            print(f"    - Footnote {fn}: \"{title}\" -- no match found")

    # Flag unverified
    unverified = [r for r in results if r["status"] == "unverified"]
    if unverified:
        print()
        print("  [!] Unverified (manual review):")
        for u in unverified[:5]:
            fn = u.get("footnote_number", "?")
            title = u.get("extracted_title", "?")[:60]
            print(f"    - Footnote {fn}: \"{title}\"")
        if len(unverified) > 5:
            print(f"    ... and {len(unverified) - 5} more")

    print(f"\n  Audit report written to: {output_path}")


# -- CLI ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Phase 1.5: Verify existing citations against academic APIs"
    )
    parser.add_argument(
        "--mode", required=True, choices=["inline", "footnotes"],
        help="Verification mode: 'inline' for \\cite bib entries, "
             "'footnotes' for extracted footnote citations",
    )
    parser.add_argument(
        "--citations", default=None,
        help="[inline] Path to existing_citations.json",
    )
    parser.add_argument(
        "--bib", default=None,
        help="[inline] Path to existing .bib file",
    )
    parser.add_argument(
        "--footnotes", default=None,
        help="[footnotes] Path to existing_footnotes.json",
    )
    parser.add_argument(
        "--output", required=True,
        help="Path to write audit_report.json",
    )
    parser.add_argument(
        "--spreadsheet", default=None,
        help="Optional .xlsx for overlap detection",
    )
    args = parser.parse_args()

    if args.mode == "inline":
        missing = []
        if not args.citations:
            missing.append("--citations")
        if not args.bib:
            missing.append("--bib")
        if missing:
            print(
                f"Error: --mode inline requires {' and '.join(missing)}",
                file=sys.stderr,
            )
            sys.exit(2)

        if not Path(args.citations).is_file():
            print(f"Error: Citations file not found: {args.citations}", file=sys.stderr)
            sys.exit(1)
        if not Path(args.bib).is_file():
            print(f"Error: Bib file not found: {args.bib}", file=sys.stderr)
            sys.exit(1)

        process_inline(args.citations, args.bib, args.output, args.spreadsheet)

    else:  # footnotes
        if not args.footnotes:
            print("Error: --mode footnotes requires --footnotes", file=sys.stderr)
            sys.exit(2)

        if not Path(args.footnotes).is_file():
            print(f"Error: Footnotes file not found: {args.footnotes}", file=sys.stderr)
            sys.exit(1)

        process_footnotes(args.footnotes, args.output, args.spreadsheet)


if __name__ == "__main__":
    main()
