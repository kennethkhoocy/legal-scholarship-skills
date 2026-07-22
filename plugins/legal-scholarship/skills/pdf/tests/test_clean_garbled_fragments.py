"""Tests for clean_garbled_fragments.py — garbled vector-figure text removal.

The cleaner must aggressively remove leaked figure-label fragments while never
touching LaTeX math, tables, captions, images, or ordinary prose.
"""

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import clean_garbled_fragments as cgf


# --- line classifier unit tests ----------------------------------------------


@pytest.mark.parametrize("line", [
    "~- · · ··· - -- - - - - -,",
    "- .. .. .  - ... --------1",
    "1-<;;:::---~...,._  _________",
    "§,,(rr)",
    ": • ..  ••",
])
def test_is_noise_detects_stroke_artifacts(line):
    assert cgf._is_noise(line) is True


@pytest.mark.parametrize("line", [
    "| a | b |",            # table row — pipe excluded from noise
    "|-------|-------|",    # table separator
    "This is ordinary prose with plenty of letters.",
    "Smith, J.",            # a name — high alphanumeric ratio
])
def test_is_noise_rejects_real_content(line):
    assert cgf._is_noise(line) is False


@pytest.mark.parametrize("line", ["= 0", "{3 *", "/3 *", "(d)", "Âo", "g_(rr)", "d", "0"])
def test_is_junk_detects_garbled_tokens(line):
    assert cgf._is_junk(line) is True


@pytest.mark.parametrize("line", ["Full Deterrence", "Partial Deterrence", "Optimal incentive"])
def test_is_junk_rejects_plain_short_phrases(line):
    # Plain short phrases are fragments but NOT junk on their own.
    assert cgf._is_junk(line) is False


def test_is_boundary_excludes_stroke_art_that_looks_like_a_list():
    # "- .. .." starts like a list item but is line-art debris → not a boundary.
    assert cgf._is_boundary("- .. .. .  - ... --------1") is False
    # A real list item is a boundary.
    assert cgf._is_boundary("- 46 This is a real footnote with text.") is True


def test_protected_mask_covers_math_blocks():
    lines = ["before", "$$", r"\beta^{*} = 0", "$$", "after"]
    mask = cgf._protected_mask(lines)
    assert mask == [False, True, True, True, False]


# --- end-to-end document cleaning --------------------------------------------


GARBLED_DOC = """# Section 4

This is a real paragraph of prose that should never be removed because it is a complete sentence.

![image](data:image/png;base64,AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKK)

(d)
Liability
Full  Deterrence
{3 *
=  0
~- · · ··· - -- - - -
Prob. Informed (rr)
Âo

Figure 1: Equilibrium Characterization

Here is a display equation that must survive intact:

$$
\\beta ^ { * } = \\frac { e } { 1 - \\alpha } \\geq 0
$$

The inline term $x_i$ also matters and this sentence runs long enough to be kept.

| Col A | Col B |
|-------|-------|
| a1    | b1    |

Smith, J.
Doe, A.
Lee, K.

This closing line is ordinary prose and clearly long enough to remain in place.
"""


@pytest.fixture
def cleaned():
    out, reports = cgf.clean(GARBLED_DOC)
    return out, reports


def test_removes_garbled_word_fragments(cleaned):
    out, _ = cleaned
    for frag in ["Full  Deterrence", "{3 *", "Prob. Informed (rr)", "Âo", "(d)"]:
        assert frag not in out


def test_removes_stroke_noise(cleaned):
    out, _ = cleaned
    assert "~- · · ··· - -- - - -" not in out


def test_preserves_latex_block(cleaned):
    out, _ = cleaned
    assert "$$" in out
    assert r"\frac { e } { 1 - \alpha }" in out
    assert r"\beta ^ { * }" in out


def test_preserves_inline_math_sentence(cleaned):
    out, _ = cleaned
    assert "$x_i$" in out


def test_preserves_figure_image_and_caption(cleaned):
    out, _ = cleaned
    assert "![image]" in out
    assert "Figure 1: Equilibrium Characterization" in out


def test_preserves_table(cleaned):
    out, _ = cleaned
    assert "| Col A | Col B |" in out
    assert "| a1    | b1    |" in out


def test_preserves_prose(cleaned):
    out, _ = cleaned
    assert "should never be removed because it is a complete sentence" in out
    assert "ordinary prose and clearly long enough" in out


def test_preserves_short_name_list_without_junk(cleaned):
    """A run of short lines with no junk tokens and not figure-adjacent must stay."""
    out, _ = cleaned
    for name in ["Smith, J.", "Doe, A.", "Lee, K."]:
        assert name in out


def test_reports_the_removed_run(cleaned):
    _, reports = cleaned
    assert len(reports) >= 1
    assert any("Deterrence" in r["sample"] or "{3" in r["sample"] for r in reports)


def test_clean_is_idempotent(cleaned):
    out, _ = cleaned
    out2, reports2 = cgf.clean(out)
    assert out2 == out
    assert reports2 == []


def test_clean_leaves_clean_document_untouched():
    doc = "# Title\n\nA normal paragraph that is long enough to be prose.\n\n$$\n\\alpha = 1\n$$\n"
    out, reports = cgf.clean(doc)
    assert reports == []
    assert out == doc
