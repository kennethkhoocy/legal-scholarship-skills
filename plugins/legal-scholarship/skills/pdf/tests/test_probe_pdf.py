"""Tests for probe_pdf.py classifier."""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import probe_pdf


def test_encrypted_pdf_is_classified_encrypted(encrypted_pdf):
    result = probe_pdf.probe(str(encrypted_pdf))
    assert result["classification"] == "encrypted"
    assert result["encrypted"] is True
    assert result["recommended_backend"] == "halt_password_required"


def test_scanned_pdf_is_classified_scanned(scanned_pdf):
    result = probe_pdf.probe(str(scanned_pdf))
    assert result["classification"] == "scanned"
    assert result["text_layer_coverage"] < probe_pdf.TUNE_TEXT_LAYER_SCANNED_MAX
    assert result["recommended_backend"] == "lightonocr"


def test_simple_pdf_has_high_text_layer_coverage(simple_pdf):
    result = probe_pdf.probe(str(simple_pdf))
    # We're not yet asserting the classification here (that's Task 9c) — only
    # confirming the measurement of text_layer_coverage is sensible.
    assert result["text_layer_coverage"] > probe_pdf.TUNE_TEXT_LAYER_SIMPLE_MIN
    assert result["cid_ratio"] < 0.1


def test_tabular_pdf_classifies_as_born_digital_tables_or_complex(tabular_pdf):
    result = probe_pdf.probe(str(tabular_pdf))
    # Either born_digital_tables or born_digital_complex is acceptable — both route
    # to opendataloader hybrid or pdfplumber, which both handle tables well.
    assert result["classification"] in ("born_digital_tables", "born_digital_complex")
    assert result["table_density"] > 0.0


def test_complex_pdf_classifies_as_born_digital_complex(complex_pdf):
    result = probe_pdf.probe(str(complex_pdf))
    assert result["classification"] == "born_digital_complex"
    assert result["image_density"] > 0.0
    assert result["complexity_score"] >= probe_pdf.TUNE_COMPLEXITY_COMPLEX_MIN
    assert result["recommended_backend"] == "opendataloader_hybrid"


def test_simple_pdf_classifies_as_born_digital_simple(simple_pdf):
    result = probe_pdf.probe(str(simple_pdf))
    assert result["classification"] == "born_digital_simple"
    assert result["recommended_backend"] == "pypdf"


def test_probe_output_has_all_expected_keys(simple_pdf):
    result = probe_pdf.probe(str(simple_pdf))
    expected_keys = {
        "page_count", "encrypted", "text_layer_coverage", "cid_ratio",
        "image_density", "table_density", "formula_density", "footnote_density",
        "complexity_score", "classification", "recommended_backend", "reasoning",
        "warnings",
    }
    assert set(result.keys()) == expected_keys


def test_probe_nonexistent_file_returns_error(tmp_path):
    nonexistent = tmp_path / "does_not_exist.pdf"
    result = probe_pdf.probe(str(nonexistent))
    assert result["classification"] == "error"
    assert result["recommended_backend"] == "fallback"
    assert "could not be read" in result["reasoning"].lower() or "no such" in result["reasoning"].lower()


def test_cli_emits_json_to_stdout(simple_pdf, tmp_path):
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "probe_pdf.py"), str(simple_pdf)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert "classification" in parsed
    assert "recommended_backend" in parsed


def test_cli_respects_sample_flag(simple_pdf):
    """--sample 1 should still produce a valid classification (using only the first page)."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "probe_pdf.py"), str(simple_pdf), "--sample", "1"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["classification"] != "error"


def test_sampled_page_indices_respects_sample_size_5():
    # 5 indices over 100 pages → 5 evenly-spaced
    result = probe_pdf._sampled_page_indices(100, 5)
    assert len(result) == 5
    assert result[0] == 0
    assert result[-1] == 99


def test_sampled_page_indices_rejects_zero():
    with pytest.raises(ValueError):
        probe_pdf._sampled_page_indices(10, 0)


def test_sampled_page_indices_small_pdf_returns_all_pages():
    result = probe_pdf._sampled_page_indices(2, 3)
    assert result == [0, 1]


def test_classifier_precedence_tables_beats_simple():
    """High table_density should win over low complexity_score."""
    classification, backend, _ = probe_pdf._classify(
        text_layer_coverage=1000,
        cid_ratio=0.0,
        image_density=0.0,
        table_density=0.5,
        complexity_score=0.05,
    )
    assert classification == "born_digital_tables"
    assert backend == "pdfplumber"


# --- I-3: probe-failure warnings + safe downgrade -----------------------------


def test_classifier_downgrades_simple_to_uncertain_when_warnings_present():
    """If density probes failed, a would-be 'simple' verdict must not route to pypdf."""
    classification, backend, reasoning = probe_pdf._classify(
        text_layer_coverage=1000,
        cid_ratio=0.0,
        image_density=0.0,
        table_density=0.0,
        complexity_score=0.0,
        has_probe_warnings=True,
    )
    assert classification == "uncertain"
    assert backend == "opendataloader_hybrid"
    assert "warnings" in reasoning.lower()


def test_classifier_simple_verdict_unchanged_when_no_warnings():
    """Without warnings, the classic 'simple' path still routes to pypdf."""
    classification, backend, _ = probe_pdf._classify(
        text_layer_coverage=1000,
        cid_ratio=0.0,
        image_density=0.0,
        table_density=0.0,
        complexity_score=0.0,
        has_probe_warnings=False,
    )
    assert classification == "born_digital_simple"
    assert backend == "pypdf"


def test_probe_records_warning_when_image_density_helper_fails(simple_pdf, mocker):
    """A pdfplumber crash inside image-density measurement must surface in JSON
    output AND must prevent the classifier from labeling the PDF 'simple'.
    Regression guard for Codex v5b finding I-3.
    """
    real_open = __import__("pdfplumber").open
    call_count = {"n": 0}

    def faulty_open(path, *args, **kwargs):
        # Fail on the FIRST pdfplumber.open call (image_density), let the
        # second succeed (table_density) so the probe still completes.
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("corrupt")
        return real_open(path, *args, **kwargs)

    mocker.patch("pdfplumber.open", side_effect=faulty_open)

    result = probe_pdf.probe(str(simple_pdf))

    # Warning must be present in the JSON output.
    assert "warnings" in result
    assert any("image_density" in w for w in result["warnings"])
    assert any("corrupt" in w for w in result["warnings"])

    # The classifier must NOT have routed this to pypdf as 'simple' — the
    # density signal is suspect, so we degrade to uncertain.
    assert result["classification"] != "born_digital_simple"
    assert result["recommended_backend"] != "pypdf"


def test_probe_warnings_reset_between_calls(simple_pdf, mocker):
    """A failure in probe A must not leak warnings into probe B."""
    real_open = __import__("pdfplumber").open

    # First call: force a failure on image_density.
    state = {"first_call": True}

    def first_run_faulty(path, *args, **kwargs):
        if state["first_call"]:
            state["first_call"] = False
            raise RuntimeError("first run failure")
        return real_open(path, *args, **kwargs)

    mocker.patch("pdfplumber.open", side_effect=first_run_faulty)
    first = probe_pdf.probe(str(simple_pdf))
    assert any("image_density" in w for w in first["warnings"])

    # Second call: no failures (real_open works); warnings must be empty.
    mocker.patch("pdfplumber.open", side_effect=real_open)
    second = probe_pdf.probe(str(simple_pdf))
    assert second["warnings"] == []


# --- Formula routing: math-heavy born-digital PDFs must reach a LaTeX-capable
#     backend (opendataloader --enrich-formula), never pypdf. --------------------


@pytest.mark.parametrize(
    "fontname",
    [
        "IETDNW+CMMI12",   # Computer Modern math italic (real subset name from a TeX PDF)
        "WTDCET+CMMI10",
        "WWOKUS+CMMI7",
        "UZPVFS+CMSY10",   # Computer Modern math symbols
        "XCSGQA+CMSY8",
        "GIMCAH+CMEX10",   # Computer Modern large math operators
        "ABCDEF+MSBM10",   # AMS blackboard-bold
        "ABCDEF+MSAM10",   # AMS symbols
        "CambriaMath",     # MS Office OMML equations
        "STIXTwoMath-Regular",
        "LatinModernMath-Regular",
    ],
)
def test_fontname_is_math_recognizes_math_fonts(fontname):
    assert probe_pdf._fontname_is_math(fontname) is True


@pytest.mark.parametrize(
    "fontname",
    [
        "ETSSDN+CMR12",    # Computer Modern ROMAN — body text, NOT math
        "LTTYXQ+CMR10",
        "ZGZMBW+CMBX12",   # Computer Modern bold extended — body text
        "ABCDEF+CMTI10",   # Computer Modern text italic — body text
        "Times-Roman",
        "Times-Italic",
        "Roboto-Regular",
        "OIRTVB+ArialMT",
        "Helvetica",
        "",
    ],
)
def test_fontname_is_math_rejects_body_fonts(fontname):
    assert probe_pdf._fontname_is_math(fontname) is False


def test_classifier_formulas_beats_simple():
    """A clean single-column math paper must NOT route to pypdf."""
    classification, backend, reasoning = probe_pdf._classify(
        text_layer_coverage=1700,
        cid_ratio=0.0,
        image_density=0.0,
        table_density=0.0,
        complexity_score=0.0,
        formula_density=0.67,
    )
    assert classification == "born_digital_formulas"
    assert backend == "opendataloader_hybrid"
    assert "--enrich-formula" in reasoning


def test_classifier_formulas_beats_tables():
    """Formula-dense content wins over tables: opendataloader keeps both."""
    classification, backend, _ = probe_pdf._classify(
        text_layer_coverage=1700,
        cid_ratio=0.0,
        image_density=0.0,
        table_density=0.5,
        complexity_score=0.2,
        formula_density=0.5,
    )
    assert classification == "born_digital_formulas"
    assert backend == "opendataloader_hybrid"


def test_classifier_footnotes_route_to_docling():
    """A footnote-dense born-digital paper goes to the Docling-direct backend."""
    classification, backend, reasoning = probe_pdf._classify(
        text_layer_coverage=1700,
        cid_ratio=0.0,
        image_density=0.0,
        table_density=0.0,
        complexity_score=0.0,
        formula_density=0.0,
        footnote_density=0.6,
    )
    assert classification == "born_digital_footnotes"
    assert backend == "docling"
    assert "docling_extract" in reasoning


def test_classifier_footnotes_beat_formulas():
    """A paper with both footnotes and math routes to docling (handles both)."""
    classification, backend, _ = probe_pdf._classify(
        text_layer_coverage=1700,
        cid_ratio=0.0,
        image_density=0.0,
        table_density=0.0,
        complexity_score=0.0,
        formula_density=0.7,
        footnote_density=0.6,
    )
    assert classification == "born_digital_footnotes"
    assert backend == "docling"


def test_classifier_scanned_beats_footnotes():
    classification, backend, _ = probe_pdf._classify(
        text_layer_coverage=10,
        cid_ratio=0.0,
        image_density=0.0,
        table_density=0.0,
        complexity_score=0.0,
        footnote_density=0.9,
    )
    assert classification == "scanned"
    assert backend == "lightonocr"


def test_classifier_scanned_beats_formulas():
    """A scanned math paper still goes to lightonocr (which also emits LaTeX)."""
    classification, backend, _ = probe_pdf._classify(
        text_layer_coverage=10,
        cid_ratio=0.0,
        image_density=0.0,
        table_density=0.0,
        complexity_score=0.0,
        formula_density=0.9,
    )
    assert classification == "scanned"
    assert backend == "lightonocr"


def test_classifier_uncertain_escalates_to_lightonocr():
    """Mixed signals route to opendataloader first, then lightonocr — not dolphin."""
    classification, backend, _ = probe_pdf._classify(
        text_layer_coverage=300,
        cid_ratio=0.0,
        image_density=0.0,
        table_density=0.0,
        complexity_score=0.15,
    )
    assert classification == "uncertain"
    assert backend == "opendataloader_then_lightonocr"


def test_classifier_below_formula_threshold_stays_simple():
    """A stray math glyph on few pages must not over-route prose to formulas."""
    classification, backend, _ = probe_pdf._classify(
        text_layer_coverage=1700,
        cid_ratio=0.0,
        image_density=0.0,
        table_density=0.0,
        complexity_score=0.0,
        formula_density=probe_pdf.TUNE_FORMULA_DENSITY_FORMULAS_MIN - 0.05,
    )
    assert classification == "born_digital_simple"
    assert backend == "pypdf"


def test_measure_formula_density_detects_broadened_glyphs(formula_pdf):
    """The synthetic math fixture should read as highly formula-dense."""
    result = probe_pdf.probe(str(formula_pdf))
    assert result["formula_density"] >= probe_pdf.TUNE_FORMULA_DENSITY_FORMULAS_MIN


def test_formula_pdf_classifies_as_born_digital_formulas(formula_pdf):
    """End-to-end: a math-glyph-dense PDF routes to opendataloader, not pypdf."""
    result = probe_pdf.probe(str(formula_pdf))
    assert result["classification"] == "born_digital_formulas"
    assert result["recommended_backend"] == "opendataloader_hybrid"
    assert result["recommended_backend"] != "pypdf"


def test_simple_pdf_is_not_misread_as_formulas(simple_pdf):
    """Plain lorem-ipsum prose carries no math signal → stays simple."""
    result = probe_pdf.probe(str(simple_pdf))
    assert result["formula_density"] == 0.0
    assert result["classification"] == "born_digital_simple"


# --- Audit fix #5: footnote density must not be fooled by numbered headings ----


class _FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class _FakeReader:
    def __init__(self, page_texts):
        self.pages = [_FakePage(t) for t in page_texts]


def test_measure_footnote_density_ignores_numbered_section_headings():
    """Numbered section headings ('1 Introduction', '2 Methods') match the
    definition pattern but have no in-body markers, so they must NOT register as
    footnote-bearing — otherwise ordinary prose misroutes to Docling."""
    reader = _FakeReader([
        "1 Introduction\nThis study examines markets.\n2 Methods\nWe collect data.\n",
        "3 Results\nThe estimates are large.\n4 Discussion\nImplications follow.\n",
    ])
    assert probe_pdf._measure_footnote_density(reader, [0, 1]) == 0.0


def test_measure_footnote_density_detects_real_footnotes():
    """A page with in-body markers AND definition lines reads as footnote-bearing."""
    reader = _FakeReader([
        "The firm disclosed.5 Investors agreed.6 The end.\n"
        "5. See Atkins (2018).\n6. See Graf (2018).\n",
    ])
    assert probe_pdf._measure_footnote_density(reader, [0]) == 1.0


def test_measure_footnote_density_empty_sample_is_zero():
    assert probe_pdf._measure_footnote_density(_FakeReader([]), []) == 0.0
