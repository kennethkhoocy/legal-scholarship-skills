"""Validate, audit, and extract footnotes from the synthetic input.docx.

Replaces the old print-driven script. Every output goes to pytest's tmp_path;
nothing is written into the skill tree and no absolute paths are hard-coded.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/core on sys.path so docx_support imports as a package (also set by
# conftest.py; repeated here so the module imports standalone).
_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parent.parent / "scripts" / "core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from docx_support.audit_ooxml import validate_docx  # noqa: E402
from docx_support.converter import (  # noqa: E402
    latex_footnote_to_plain,
    validate_and_extract,
)
from docx_support.footnotes import (  # noqa: E402
    extract_footnote_locations,
    extract_footnotes,
)

import make_fixture  # noqa: E402

FIXTURE = _HERE / "input.docx"
EXPECTED_TEXTS = make_fixture.EXPECTED_TEXTS


def test_validate_docx_reports_no_errors():
    diags = validate_docx(FIXTURE)
    errors = [d for d in diags if d.level == "error"]
    assert errors == [], f"validate_docx reported errors: {[e.message for e in errors]}"


def test_extract_footnotes_returns_five_planted_texts():
    footnotes = extract_footnotes(FIXTURE)
    assert len(footnotes) == 5, f"expected 5 footnotes, got {len(footnotes)}"

    ordered = sorted(footnotes, key=lambda f: f["footnote_id"])
    texts = [f["text"] for f in ordered]
    assert texts == EXPECTED_TEXTS, f"extracted texts diverge: {texts}"


def test_extract_footnote_locations_have_valid_indexes():
    locations = extract_footnote_locations(FIXTURE)
    assert len(locations) == 5, f"expected 5 locations, got {len(locations)}"

    # One reference per planted footnote id.
    assert {loc["footnote_id"] for loc in locations} == {1, 2, 3, 4, 5}

    for loc in locations:
        assert isinstance(loc["paragraph_index"], int)
        assert loc["paragraph_index"] >= 0


def test_validate_and_extract_writes_all_outputs(tmp_path):
    result = validate_and_extract(FIXTURE, tmp_path)
    assert result["valid"] is True
    assert len(result["footnotes"]) == 5
    assert len(result["footnote_locations"]) == 5

    for name in ("paragraphs.json", "document.md", "footnotes.json",
                 "footnote_locations.json"):
        out = tmp_path / name
        assert out.exists(), f"validate_and_extract did not write {name}"
        assert out.stat().st_size > 0, f"{name} is empty"


def test_latex_footnote_to_plain_converts_sensibly():
    sample = (
        r"See Jeffrey N. Gordon, \textit{The Rise of Independent Directors}, "
        r"59 \textsc{Stan.\ L.\ Rev.}\ 1465 (2007)."
    )
    plain = latex_footnote_to_plain(sample)

    # \textit -> *...* markers, \textsc -> upper-cased small caps.
    assert "*The Rise of Independent Directors*" in plain
    assert "STAN. L. REV." in plain
    # LaTeX command markup is gone.
    assert r"\textit" not in plain
    assert r"\textsc" not in plain
    assert "1465 (2007)" in plain
