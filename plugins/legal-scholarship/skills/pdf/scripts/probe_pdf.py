"""Probe a PDF and emit a JSON classification + backend recommendation.

Outputs a JSON object to stdout describing:
  - encrypted, page_count, text_layer_coverage, cid_ratio, image_density,
    table_density, formula_density, complexity_score
  - classification (one of: encrypted, scanned, born_digital_footnotes,
    born_digital_simple, born_digital_formulas, born_digital_tables,
    born_digital_complex, uncertain, error)
  - recommended_backend (one of: halt_password_required, lightonocr, docling, pypdf,
    pdfplumber, opendataloader_hybrid, opendataloader_then_lightonocr, fallback)
  - reasoning (one-sentence rationale)

Used by the pdf skill's SKILL.md as Step 1 of every PDF task.

Usage:
    python probe_pdf.py <input.pdf> [--sample N]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

# Threshold constants — first-pass values, marked TUNE for empirical adjustment.
TUNE_TEXT_LAYER_SCANNED_MAX = 50         # < this chars/page → scanned
TUNE_TEXT_LAYER_SIMPLE_MIN = 500         # > this chars/page → born-digital
TUNE_CID_RATIO_SCANNED_MIN = 0.3         # > this (cid:N) ratio → scanned
TUNE_COMPLEXITY_SIMPLE_MAX = 0.1         # < this complexity → simple
TUNE_COMPLEXITY_COMPLEX_MIN = 0.2        # > this complexity → complex
TUNE_TABLE_DENSITY_TABLES_MIN = 0.3      # > this table density → tables
TUNE_FORMULA_DENSITY_FORMULAS_MIN = 0.2  # > this fraction of math-bearing pages → formula-heavy
TUNE_FOOTNOTE_DENSITY_MIN = 0.5          # >= this fraction of footnote-bearing pages → academic/footnoted

# Probe-failure breadcrumbs. Helpers that swallow an exception append a string
# here so the classifier can downgrade a borderline "simple" verdict to
# "uncertain" instead of routing a corrupt or weird PDF to pypdf. Reset at the
# top of each probe() call so test-to-test contamination doesn't happen.
_PROBE_WARNINGS: list[str] = []

# --- Math-detection signals (used by _measure_formula_density) ----------------
#
# Two complementary, high-precision signals decide whether a page carries math:
#   1. Math FONT families in char metadata (encoding-independent — fires even
#      when the math is subset-encoded so the text layer yields no usable
#      Unicode). This is the dominant signal for TeX-produced papers.
#   2. A broadened set of Unicode math GLYPHS in the extracted text layer.
#
# Body-text families are deliberately excluded: Computer Modern Roman (CMR),
# bold extended (CMBX), and text italic (CMTI) are NOT math fonts. Only the
# genuine math families below count.
import re as _re

_MATH_FONT_RE = _re.compile(
    r"(?:"
    r"CMMI|CMSY|CMEX|CMBSY|"               # Computer Modern math (italic/symbol/ext/bold-symbol)
    r"MSAM|MSBM|"                          # AMS symbol fonts
    r"RSFS|EUFM|EUFB|EUSM|EUSB|EUEX|"      # script / Euler families
    r"BBOLD|DSROM|"                        # blackboard-bold families
    r"STIX\w*Math|XITS\w*Math|"            # STIX / XITS math
    r"LMMath|LatinModernMath|"             # Latin Modern Math (OpenType)
    r"CambriaMath|Cambria-Math|"           # MS Office / OMML equations
    r"Asana-?Math|NotoSans\w*Math|NotoSerif\w*Math|DejaVu\w*Math|"
    r"TeXGyre\w*Math|"                     # OpenType math families
    r"esint|wasy|stmary"                   # extra symbol packages
    r")",
    _re.IGNORECASE,
)

# Broadened math-glyph set: operators, relations, set/logic, arrows,
# blackboard letters, delimiters/primes, sub/superscripts, and the Greek
# letters used in mathematics.
_MATH_GLYPHS = frozenset(
    "∫∬∭∮∯∑∏∐∂∇√∛∜∝∞∠∡∢"            # operators
    "±∓×÷⋅∘∙⊗⊕⊖⊙⊘⊚⊛∗⋆"              # binary operators
    "≈≃≅≆≇≊≋≜≝≞≟≡≢≠≤≥≦≧≪≫⪅⪆⩽⩾"      # relations
    "∼∽≀∥∦⊥"
    "⊂⊃⊆⊇⊄⊅⊊⊋∈∉∋∌∅"                # set theory
    "∀∃∄∧∨¬⊻⊼⊽∩∪⊎⊍⊤⊢⊣⊨"            # logic
    "→←↔⇒⇐⇔↦⟶⟵⟷⟹⟸⟺↪↩"            # arrows
    "ℝℂℤℕℚℙℍℾℶℵℓ℘ℏℑℜ"              # blackboard / special letters
    "⌈⌉⌊⌋⟨⟩‖′″‴⁗"                  # delimiters / primes
    "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ"            # superscripts
    "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₓ"            # subscripts
    "αβγδεζηθικλμνξπρστυφχψω"        # Greek lower (math)
    "ϵϑϰϕϱϖ"                         # Greek variant forms
    "ΓΔΘΛΞΠΣΦΨΩ"                    # Greek upper (math)
    "∴∵∎□∖∆"
)


def _fontname_is_math(fontname: str) -> bool:
    """True if a PDF font name belongs to a known math font family.

    Handles the 6-letter subset prefix PDFs prepend (e.g. ``IETDNW+CMMI12``):
    the regex searches anywhere in the name. Body-text families (CMR, CMBX,
    CMTI, Times, Arial, ...) return False.
    """
    if not fontname:
        return False
    return _MATH_FONT_RE.search(fontname) is not None


def probe(pdf_path: str, sample_size: int = 3) -> dict[str, Any]:
    """Return a classification dict for the PDF at pdf_path."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    # Reset breadcrumbs so a previous probe in the same process doesn't bleed
    # warnings into this one (matters in tests and long-running services).
    _PROBE_WARNINGS.clear()

    # Check encryption first — fails early without trying to parse content
    try:
        reader = PdfReader(pdf_path)
    except (PdfReadError, FileNotFoundError) as e:
        return _error_result(pdf_path, f"PDF could not be read: {e}")

    if reader.is_encrypted:
        return {
            "page_count": 0,  # pypdf can't enumerate pages without the password
            "encrypted": True,
            "text_layer_coverage": 0,
            "cid_ratio": 0.0,
            "image_density": 0.0,
            "table_density": 0.0,
            "formula_density": 0.0,
            "footnote_density": 0.0,
            "complexity_score": 0.0,
            "classification": "encrypted",
            "recommended_backend": "halt_password_required",
            "reasoning": "PDF is encrypted; ask the user for a password before re-probing.",
            "warnings": [],
        }

    # Sample pages for measurement (first / middle / last to keep probe fast on large PDFs)
    page_count = len(reader.pages)
    sampled_indices = _sampled_page_indices(page_count, sample_size)

    text_layer_coverage, cid_ratio = _measure_text_layer(reader, sampled_indices)
    image_density = _measure_image_density(pdf_path, sampled_indices)
    table_density = _measure_table_density(pdf_path, sampled_indices)
    formula_density = _measure_formula_density(reader, pdf_path, sampled_indices)
    footnote_density = _measure_footnote_density(reader, sampled_indices)
    complexity_score = 0.6 * image_density + 0.4 * table_density

    classification, backend, reasoning = _classify(
        text_layer_coverage=text_layer_coverage,
        cid_ratio=cid_ratio,
        image_density=image_density,
        table_density=table_density,
        complexity_score=complexity_score,
        formula_density=formula_density,
        footnote_density=footnote_density,
        has_probe_warnings=bool(_PROBE_WARNINGS),
    )

    return {
        "page_count": page_count,
        "encrypted": False,
        "text_layer_coverage": round(text_layer_coverage, 1),
        "cid_ratio": round(cid_ratio, 3),
        "image_density": round(image_density, 3),
        "table_density": round(table_density, 3),
        "formula_density": round(formula_density, 3),
        "footnote_density": round(footnote_density, 3),
        "complexity_score": round(complexity_score, 3),
        "classification": classification,
        "recommended_backend": backend,
        "reasoning": reasoning,
        "warnings": list(_PROBE_WARNINGS),
    }


def _error_result(pdf_path: str, reason: str) -> dict[str, Any]:
    return {
        "page_count": 0,
        "encrypted": False,
        "text_layer_coverage": 0,
        "cid_ratio": 0.0,
        "image_density": 0.0,
        "table_density": 0.0,
        "formula_density": 0.0,
        "footnote_density": 0.0,
        "complexity_score": 0.0,
        "classification": "error",
        "recommended_backend": "fallback",
        "reasoning": reason,
        "warnings": list(_PROBE_WARNINGS),
    }


def _sampled_page_indices(page_count: int, sample_size: int) -> list[int]:
    """Pick evenly-spaced indices. For sample_size >= page_count, return all pages.

    sample_size <= 0 raises ValueError.
    """
    if sample_size <= 0:
        raise ValueError(f"sample_size must be >= 1, got {sample_size}")
    if page_count <= 0:
        return []
    if page_count <= sample_size:
        return list(range(page_count))
    if sample_size == 1:
        return [0]
    # Evenly-spaced (rounded) — always includes first and last
    return sorted({round(i * (page_count - 1) / (sample_size - 1)) for i in range(sample_size)})


def _measure_text_layer(reader, sampled_indices: list[int]) -> tuple[float, float]:
    """Mean chars/page across sampled pages, plus (cid:N) ratio."""
    import re
    cid_re = re.compile(r"\(cid:\d+\)")
    if not sampled_indices:
        return 0.0, 0.0
    total_chars = 0
    total_cid_chars = 0
    for i in sampled_indices:
        text = reader.pages[i].extract_text() or ""
        total_chars += len(text)
        total_cid_chars += sum(len(m.group()) for m in cid_re.finditer(text))
    avg = total_chars / len(sampled_indices)
    cid_ratio = (total_cid_chars / total_chars) if total_chars > 0 else 0.0
    return avg, cid_ratio


def _classify(
    text_layer_coverage: float,
    cid_ratio: float,
    image_density: float,
    table_density: float,
    complexity_score: float,
    formula_density: float = 0.0,
    footnote_density: float = 0.0,
    has_probe_warnings: bool = False,
) -> tuple[str, str, str]:
    """Return (classification, recommended_backend, reasoning) tuple.

    Precedence: scanned → footnotes → formulas → tables → simple → complex → uncertain.

    A born-digital PDF dense with footnotes (footnote_density >=
    TUNE_FOOTNOTE_DENSITY_MIN) is classified "born_digital_footnotes" and routed
    to the Docling-direct backend, which reconstructs footnotes as Markdown and
    also emits formula LaTeX. This sits above the formula branch because most
    footnoted academic papers also contain math, and Docling handles both, while
    opendataloader-pdf discards footnote structure.

    A born-digital PDF whose pages are dense with mathematics
    (formula_density >= TUNE_FORMULA_DENSITY_FORMULAS_MIN) is classified
    "born_digital_formulas" and routed to opendataloader-pdf BEFORE the simple
    and tables branches. This is deliberate: pypdf and pdfplumber flatten
    equations to broken inline text or drop them entirely, whereas
    opendataloader-pdf with --enrich-formula emits LaTeX. The check sits after
    "scanned" so that a truly scanned math paper still goes to LightOnOCR (which
    also produces LaTeX for formulas). opendataloader-pdf handles tables and
    multi-column layout too, so promoting formulas above tables/complex costs
    nothing in those dimensions while preserving the math.

    When has_probe_warnings is True, a verdict of "born_digital_simple" is
    downgraded to "uncertain" with an opendataloader recommendation. The
    density measurements that drive the "simple" verdict are exactly the ones
    that can silently return 0.0 when their helpers swallow an exception
    (image_density, table_density). Routing such PDFs to pypdf risks garbage
    extraction; opendataloader is the safer complex-capable default.
    """
    if text_layer_coverage < TUNE_TEXT_LAYER_SCANNED_MAX or cid_ratio > TUNE_CID_RATIO_SCANNED_MIN:
        return (
            "scanned",
            "lightonocr",
            f"Text layer is thin ({text_layer_coverage:.0f} chars/page) or has high "
            f"(cid:N) ratio ({cid_ratio:.2f}). PDF appears scanned or has subset fonts; "
            f"use LightOnOCR-2-1B (scripts/lightonocr_run.py) for vision-LM OCR; "
            f"dolphin v2 is the fallback.",
        )
    if footnote_density >= TUNE_FOOTNOTE_DENSITY_MIN:
        also_math = formula_density >= TUNE_FORMULA_DENSITY_FORMULAS_MIN
        return (
            "born_digital_footnotes",
            "docling",
            f"Born-digital, footnote-dense (footnote_density={footnote_density:.2f}"
            f"{', math too' if also_math else ''}). Use scripts/docling_extract.py: it "
            f"reconstructs footnotes as Markdown ([^n] markers + definitions) and emits "
            f"formula LaTeX, whereas opendataloader-pdf discards footnote structure. Follow "
            f"with the KaTeX-sanitize pass (sanitize_math.py).",
        )
    if formula_density >= TUNE_FORMULA_DENSITY_FORMULAS_MIN:
        return (
            "born_digital_formulas",
            "opendataloader_hybrid",
            f"Born-digital with dense mathematics (formula_density={formula_density:.2f}). "
            f"Run opendataloader-pdf --hybrid docling-fast WITH --enrich-formula so equations "
            f"are emitted as LaTeX; pypdf/pdfplumber would flatten or drop them. Escalate to "
            f"lightonocr (scripts/lightonocr_run.py) if equations are images or the LaTeX output is sparse.",
        )
    if text_layer_coverage > TUNE_TEXT_LAYER_SIMPLE_MIN and table_density > TUNE_TABLE_DENSITY_TABLES_MIN:
        return (
            "born_digital_tables",
            "pdfplumber",
            f"Born-digital with table_density={table_density:.2f}. "
            f"Use pdfplumber.extract_tables() for accurate table reconstruction.",
        )
    if (text_layer_coverage > TUNE_TEXT_LAYER_SIMPLE_MIN and complexity_score < TUNE_COMPLEXITY_SIMPLE_MAX
            and table_density <= TUNE_TABLE_DENSITY_TABLES_MIN):
        if has_probe_warnings:
            return (
                "uncertain",
                "opendataloader_hybrid",
                f"Born-digital text ({text_layer_coverage:.0f} chars/page) but density "
                f"probes failed (see warnings); cannot safely confirm a simple layout. "
                f"Use opendataloader-pdf --hybrid docling-fast as the safe default.",
            )
        return (
            "born_digital_simple",
            "pypdf",
            f"Born-digital with clean text layer ({text_layer_coverage:.0f} chars/page) "
            f"and low complexity. Use pypdf.extract_text() for fastest results.",
        )
    if text_layer_coverage > TUNE_TEXT_LAYER_SIMPLE_MIN and complexity_score > TUNE_COMPLEXITY_COMPLEX_MIN:
        return (
            "born_digital_complex",
            "opendataloader_hybrid",
            f"Born-digital with high complexity ({complexity_score:.2f}: "
            f"image_density={image_density:.2f}, table_density={table_density:.2f}). "
            f"Use opendataloader-pdf --hybrid docling-fast for accurate layout handling.",
        )
    return (
        "uncertain",
        "opendataloader_then_lightonocr",
        f"Mixed signals (text={text_layer_coverage:.0f} chars/page, "
        f"complexity={complexity_score:.2f}). Try opendataloader-pdf first, escalate to "
        f"lightonocr if output is empty or has (cid:N) garbage.",
    )


def _measure_image_density(pdf_path: str, sampled_indices: list[int]) -> float:
    """Mean (image-area / page-area) across sampled pages, via pdfplumber."""
    import pdfplumber
    if not sampled_indices:
        return 0.0
    try:
        with pdfplumber.open(pdf_path) as pdf:
            densities = []
            for i in sampled_indices:
                if i >= len(pdf.pages):
                    continue
                page = pdf.pages[i]
                page_area = float(page.width) * float(page.height)
                if page_area <= 0:
                    continue
                image_area = sum(
                    max(0.0, (img.get("x1", 0) - img.get("x0", 0)))
                    * max(0.0, (img.get("bottom", 0) - img.get("top", 0)))
                    for img in (page.images or [])
                )
                densities.append(min(1.0, image_area / page_area))
            return sum(densities) / len(densities) if densities else 0.0
    except Exception as e:
        _PROBE_WARNINGS.append(f"image_density: {type(e).__name__}: {e}")
        return 0.0


def _measure_table_density(pdf_path: str, sampled_indices: list[int]) -> float:
    """Mean (tables_found / 1.0) across sampled pages. Capped at 1.0."""
    import pdfplumber
    if not sampled_indices:
        return 0.0
    try:
        with pdfplumber.open(pdf_path) as pdf:
            counts = []
            for i in sampled_indices:
                if i >= len(pdf.pages):
                    continue
                tables = pdf.pages[i].find_tables() or []
                counts.append(min(1.0, len(tables) / 1.0))
            return sum(counts) / len(counts) if counts else 0.0
    except Exception as e:
        _PROBE_WARNINGS.append(f"table_density: {type(e).__name__}: {e}")
        return 0.0


def _measure_formula_density(reader, pdf_path: str, sampled_indices: list[int]) -> float:
    """Fraction of sampled pages that carry a math signal.

    A page counts as math-bearing if EITHER:
      - a character on it is set in a known math font family (CMMI/CMSY/CMEX,
        AMS, Cambria Math, STIX Math, ...) — see `_fontname_is_math`, or
      - its extracted text contains a glyph from the broadened math set
        (`_MATH_GLYPHS`).

    The font signal is encoding-independent and is the decisive one for
    TeX-produced papers, where equations are often subset-encoded so the text
    layer yields little usable Unicode. The font probe (pdfplumber) is
    best-effort: if it cannot open or parse the file, the measure falls back to
    the glyph signal alone — still a valid, if weaker, reading — and does not
    record a probe warning, because a usable value was still produced.
    """
    if not sampled_indices:
        return 0.0

    # Glyph signal from the cheap pypdf text layer.
    glyph_hit = set()
    for i in sampled_indices:
        text = reader.pages[i].extract_text() or ""
        if any(ch in _MATH_GLYPHS for ch in text):
            glyph_hit.add(i)

    # Font signal from pdfplumber char metadata (best-effort).
    font_hit = set()
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for i in sampled_indices:
                if i >= len(pdf.pages):
                    continue
                for ch in (pdf.pages[i].chars or []):
                    if _fontname_is_math(ch.get("fontname", "")):
                        font_hit.add(i)
                        break
    except Exception:
        pass

    hits = len(glyph_hit | font_hit)
    return hits / len(sampled_indices)


def _measure_footnote_density(reader, sampled_indices: list[int]) -> float:
    """Fraction of sampled pages that look footnote-bearing.

    Counts two cheap signals in the pypdf text layer: in-body reference markers
    (a small number glued to a word-end and followed by a capitalised word) and
    footnote-definition starts (a line beginning with a small number). A page is
    footnote-bearing when it shows several of these. High density routes to the
    Docling-direct backend, which preserves footnote structure that
    opendataloader-pdf discards.
    """
    import re
    if not sampled_indices:
        return 0.0
    marker = re.compile(r'(?<=[a-z\.\)”"\'’])\d{1,3}(?=\s+[A-Z“"])')
    defn = re.compile(r'(?m)^\s*-?\s*\d{1,3}[.\):\s]?\s*[A-Za-z“"]')
    pages_with = 0
    for i in sampled_indices:
        text = reader.pages[i].extract_text() or ""
        markers = len(marker.findall(text))
        defns = len(defn.findall(text))
        # A single line-start number is too weak: numbered section headings
        # ("1 Introduction", "2 Methods", "3 Results") match the definition
        # pattern yet produce no in-body markers, which would route ordinary
        # prose to Docling. Require a genuine in-body marker paired with a
        # definition line, or several in-body markers, before calling a page
        # footnote-bearing.
        if (markers >= 1 and defns >= 1) or markers >= 2:
            pages_with += 1
    return pages_with / len(sampled_indices)


def main():
    ap = argparse.ArgumentParser(description="Probe a PDF and emit JSON classification.")
    ap.add_argument("pdf_path", help="Path to the input PDF")
    ap.add_argument("--sample", type=int, default=3, help="Pages to sample (default: 3)")
    args = ap.parse_args()

    if args.sample < 1:
        print(json.dumps({"classification": "error", "recommended_backend": "fallback",
                          "reasoning": f"--sample must be >= 1 (got {args.sample})"}, indent=2))
        sys.exit(1)

    result = probe(args.pdf_path, sample_size=args.sample)
    print(json.dumps(result, indent=2))
    sys.exit(1 if result["classification"] == "error" else 0)


if __name__ == "__main__":
    main()
