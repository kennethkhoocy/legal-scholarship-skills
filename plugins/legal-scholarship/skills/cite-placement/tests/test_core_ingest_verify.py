"""Offline tests for the core ingest and verify scripts.

Zero network: the verify tests monkeypatch the API-search functions, so no
socket is ever opened. Heavy imports (openpyxl, ingest_citations,
verify_citations) are performed lazily inside each test via importorskip, so
`pytest --collect-only` succeeds even while the parallel agent is still
writing scripts/core/verify_citations.py.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# scripts/core on sys.path for `import ingest_citations` / `import verify_citations`.
_CORE = Path(__file__).resolve().parent.parent / "scripts" / "core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))


# ── helpers ──────────────────────────────────────────────────────────

def _write_xlsx(path: Path, headers: list[str], rows: list[list]):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(str(path))


def _status_of(result):
    """Extract a classification label from verify_one's return.

    The contract fixes the labels (verified / hallucinated / unverified) but
    not the container. Tolerate a bare string, a (status, ...) tuple, or a
    dict carrying the label under a conventional key.
    """
    if isinstance(result, str):
        return result
    if isinstance(result, tuple) and result:
        return _status_of(result[0])
    if isinstance(result, dict):
        for key in ("status", "classification", "result", "verdict"):
            if key in result:
                return result[key]
    return result


# ── (a) ingest: cite keys, entry types, DOI dedup ────────────────────

def test_ingest_keys_types_and_doi_dedup(tmp_path):
    ingest_citations = pytest.importorskip("ingest_citations")

    xlsx = tmp_path / "citations.xlsx"
    headers = ["title", "authors", "year", "journal", "doi"]
    rows = [
        # Row A: ordinary journal article -> @article.
        ["The Economics of Widget Regulation", "Jane Q. Author", 2020,
         "Journal of Widget Studies", "10.1000/aaa"],
        # Row B: working-paper series -> @techreport.
        ["Widgets and Market Power", "John B. Scholar", 2021,
         "NBER Working Paper Series", "10.1000/bbb"],
        # Row C: DOI duplicate of an entry already in the existing .bib.
        ["Revisiting Widget Policy", "Alice Prior", 2022,
         "Journal of Widget Studies", "10.1000/ccc"],
    ]
    _write_xlsx(xlsx, headers, rows)

    existing_bib = tmp_path / "references.bib"
    existing_bib.write_text(
        "@article{prior2019widget,\n"
        "  title = {Prior Widget Work},\n"
        "  author = {Prior, Alice},\n"
        "  year = {2019},\n"
        "  journal = {Journal of Widget Studies},\n"
        "  doi = {10.1000/ccc},\n"
        "}\n",
        encoding="utf-8",
    )

    out_json = tmp_path / "citations.json"
    out_bib = tmp_path / "references_new.bib"

    ingest_citations.ingest(
        input_path=xlsx,
        output_json=out_json,
        output_bib=out_bib,
        existing_bib=existing_bib,
        min_score=0,
    )

    import json
    citations = json.loads(out_json.read_text(encoding="utf-8"))
    by_title = {c["title"]: c for c in citations}

    # Cite key format: lastnameYEARfirstword (Google-Scholar style).
    key_a = by_title["The Economics of Widget Regulation"]["cite_key"]
    assert re.fullmatch(r"[a-z]+[0-9]{4}[a-z]+", key_a), key_a
    assert key_a == "author2020economics", key_a

    # Entry types.
    assert by_title["The Economics of Widget Regulation"]["entry_type"] == "article"
    assert by_title["Widgets and Market Power"]["entry_type"] == "techreport"

    # DOI dedup: row C flagged already_in_bib and excluded from the .bib.
    dup = by_title["Revisiting Widget Policy"]
    assert dup["already_in_bib"] is True
    dup_key = dup["cite_key"]

    bib_text = out_bib.read_text(encoding="utf-8")
    assert "@article{" in bib_text
    assert "@techreport{" in bib_text
    assert dup_key not in bib_text, "duplicate entry must not appear in output .bib"

    # Only the two non-duplicate rows are written.
    entry_count = bib_text.count("@article{") + bib_text.count("@techreport{")
    assert entry_count == 2, f"expected 2 written entries, got {entry_count}"


# ── (b) verify: parse_bib_file ───────────────────────────────────────

def test_parse_bib_file(tmp_path):
    verify_citations = pytest.importorskip("verify_citations")

    bib = tmp_path / "refs.bib"
    bib.write_text(
        "@article{smith2020widgets,\n"
        "  title = {A Study of Widgets},\n"
        "  author = {Smith, John},\n"
        "  year = {2020},\n"
        "  journal = {Journal of Widget Studies},\n"
        "  doi = {10.1000/xyz},\n"
        "}\n\n"
        "@techreport{jones2019policy,\n"
        "  title = {Widget Policy Report},\n"
        "  author = {Jones, Mary},\n"
        "  year = {2019},\n"
        "  institution = {NBER},\n"
        "}\n",
        encoding="utf-8",
    )

    parsed = verify_citations.parse_bib_file(bib)
    assert set(parsed.keys()) == {"smith2020widgets", "jones2019policy"}

    smith = parsed["smith2020widgets"]
    assert smith["entry_type"] == "article"
    assert "widget" in smith["title"].lower()
    assert "smith" in smith["author"].lower()
    assert str(smith["year"]) == "2020"
    assert smith["doi"] == "10.1000/xyz"
    assert "widget" in smith["journal"].lower()

    jones = parsed["jones2019policy"]
    assert jones["entry_type"] == "techreport"
    assert "jones" in jones["author"].lower()


# ── (c) verify: verify_one classification (no sockets) ───────────────

def _openalex_hit(title):
    return {
        "title": "A Study of Widgets",
        "authors": ["John Smith"],
        "author": "John Smith",
        "year": 2020,
        "journal": "Journal of Widget Studies",
        "doi": "10.1000/xyz",
        "volume": "12",
        "pages": "345-360",
        "source": "openalex",
    }


def _openalex_miss(title):
    # Shares exactly one significant word ("Study") with the query title so the
    # best-candidate Jaccard is > 0 but < 0.5, which classifies as hallucinated
    # (a zero-overlap candidate leaves best_match unset -> unverified instead).
    return {
        "title": "Study of Quantum Chromodynamics in Distant Galaxies",
        "authors": ["Zoe Cosmos"],
        "author": "Zoe Cosmos",
        "year": 1999,
        "journal": "Astrophysics Letters",
        "doi": "",
        "volume": "",
        "pages": "",
        "source": "openalex",
    }


def _crossref_none(title):
    return None


def _entry_and_map():
    entry = {
        "title": "A Study of Widgets",
        "author": "John Smith",
        "year": 2020,
        "journal": "Journal of Widget Studies",
        "doi": "10.1000/xyz",
    }
    field_map = {
        "title": "title",
        "author": "author",
        "year": "year",
        "journal": "journal",
        "doi": "doi",
    }
    return entry, field_map


def test_verify_one_verified(monkeypatch):
    verify_citations = pytest.importorskip("verify_citations")
    monkeypatch.setattr(verify_citations, "search_openalex", _openalex_hit)
    monkeypatch.setattr(verify_citations, "search_crossref", _crossref_none)

    entry, field_map = _entry_and_map()
    result = verify_citations.verify_one(
        entry, None, field_map=field_map, capture_metadata=True
    )
    assert _status_of(result) == "verified"


def test_verify_one_hallucinated(monkeypatch):
    verify_citations = pytest.importorskip("verify_citations")
    monkeypatch.setattr(verify_citations, "search_openalex", _openalex_miss)
    monkeypatch.setattr(verify_citations, "search_crossref", _openalex_miss)

    entry, field_map = _entry_and_map()
    result = verify_citations.verify_one(
        entry, None, field_map=field_map, capture_metadata=True
    )
    assert _status_of(result) == "hallucinated"


# ── (d) verify: check_bluebook_format ────────────────────────────────

def test_check_bluebook_format_flags_full_journal_name():
    verify_citations = pytest.importorskip("verify_citations")

    abbrevs = verify_citations.BLUEBOOK_JOURNAL_ABBREVS
    # Pick a real full-name -> abbreviation pair from the module's own table,
    # e.g. "journal of finance" -> "J. Fin.".
    full, abbrev = next(iter(abbrevs.items()))

    raw = f"Some Author, A Study of Widgets, 12 {full} 100 (2020)."
    citation = {
        "raw_text": raw,
        "verified_metadata": {
            "journal": full,
            "title": "A Study of Widgets",
            "authors": ["Some Author"],
            "year": 2020,
            "volume": "12",
            "pages": "100-120",
        },
        "extracted_author": "Some Author",
        "extracted_year": 2020,
    }

    issues, corrected = verify_citations.check_bluebook_format(citation)
    assert issues, "expected a Bluebook journal-abbreviation issue"
    assert any(abbrev in issue for issue in issues)
    assert abbrev in corrected


def test_process_footnotes_accepts_object_form(tmp_path):
    """Object form ({"footnotes": [...], "citation_slots": [...]}) must verify
    like the legacy bare array (empty list -> no network, empty report)."""
    import json
    import verify_citations as vc

    src = tmp_path / "existing_footnotes.json"
    src.write_text(json.dumps({"footnotes": [], "citation_slots": [
        {"slot_id": "S1", "section": "II", "anchor": "% CITE: meta-analysis on Y",
         "hint": "meta-analysis on Y", "form": "bare"}]}), encoding="utf-8")
    out = tmp_path / "audit_report.json"
    vc.process_footnotes(str(src), str(out), None)
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["citations"] == []
    assert "summary" in report
