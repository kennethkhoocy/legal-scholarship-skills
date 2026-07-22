"""Tests for sanitize_math.py — KaTeX-safe math.

The validation-driven decision logic is tested with a fake KaTeX oracle so the
tests are deterministic and need no Node. A real-KaTeX integration test runs
when a katex install is reachable and is skipped otherwise.
"""

import re
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import sanitize_math as sm


# --- helper unit tests --------------------------------------------------------

@pytest.mark.parametrize("latex,expected", [
    (r"\frac { a } { b } = & \frac { c } { d }", True),          # bare &
    (r"x = y \\ z = w", True),                                    # bare \\
    (r"\begin{cases} a & b \\ c & d \end{cases}", False),         # & inside cases
    (r"\begin{aligned} a & = b \\ c & = d \end{aligned}", False), # & inside aligned
    (r"\alpha ^ { * } = 1 - \frac { e } { x - d }", False),       # plain equation
    (r"a \& b", False),                                           # escaped ampersand = literal
])
def test_has_top_level_alignment(latex, expected):
    assert sm._has_top_level_alignment(latex) is expected


def test_strip_envs_removes_permitting_spans():
    s = r"\begin{cases} a & b \end{cases} + x"
    assert "&" not in sm._strip_envs(s)


def test_wrap_aligned_wraps_and_trims_row_breaks():
    out = sm._wrap_aligned(r"\\ a = & b \\")
    assert out.startswith(r"\begin{aligned}")
    assert out.endswith(r"\end{aligned}")
    assert "a = & b" in out
    assert not re.search(r"aligned\}\s*\\\\", out)  # no leading row break left inside


@pytest.mark.parametrize("latex,expected", [
    ("", True),
    ("\\", True),
    ("\\\\", True),
    (r"^ { \prime } =", False),   # KaTeX renders this — NOT obvious debris
    (r"x = 1", False),
])
def test_is_obvious_debris(latex, expected):
    assert sm._is_obvious_debris(latex) is expected


# --- fake KaTeX oracle --------------------------------------------------------

class FakeKaTeX:
    """Mimics the relevant KaTeX accept/reject behaviour without Node."""
    available = True

    def validate_batch(self, items):
        return [self._ok(s) for s in items]

    @staticmethod
    def _ok(s: str) -> bool:
        t = s.strip()
        if t in ("", "\\", "\\\\"):
            return False
        if "\\intertext" in t or "\\Deltad" in t:
            return False
        top = re.sub(r"\\begin\{(cases|aligned|array|matrix|split)\}.*?\\end\{\1\}", "", t, flags=re.DOTALL)
        top = top.replace(r"\&", "")
        return "&" not in top


def _doc(*blocks: str) -> str:
    parts = ["# Heading", "", "Some prose sentence that should always survive."]
    for b in blocks:
        parts += ["", "$$", b, "$$"]
    parts += ["", "Closing prose sentence."]
    return "\n".join(parts) + "\n"


# --- validation-driven behaviour ---------------------------------------------

def test_bare_ampersand_block_is_wrapped_not_suppressed():
    doc = _doc(r"\frac { a } { b } = & \frac { c } { d }")
    out, report = sm.sanitize(doc, FakeKaTeX())
    assert report["mode"] == "katex"
    assert report["wrapped"] == 1
    assert report["suppressed"] == 0
    assert r"\begin{aligned}" in out
    assert "= & \\frac { c } { d }" in out


def test_intertext_block_is_suppressed():
    doc = _doc(r"a = b \\ \intertext{note} c = d")
    out, report = sm.sanitize(doc, FakeKaTeX())
    assert report["suppressed"] == 1
    assert "\\intertext" not in out
    assert "$$" not in out  # the only block was removed


def test_lone_backslash_block_is_suppressed():
    doc = _doc("\\")
    out, report = sm.sanitize(doc, FakeKaTeX())
    assert report["suppressed"] == 1


def test_valid_fragment_is_kept_not_suppressed():
    """Regression: `^ { \\prime } =` renders in KaTeX, so it must NOT be suppressed."""
    doc = _doc(r"^ { \prime } =")
    out, report = sm.sanitize(doc, FakeKaTeX())
    assert report["suppressed"] == 0
    assert report["kept"] == 1
    assert r"^ { \prime } =" in out


def test_plain_equation_is_untouched():
    doc = _doc(r"\alpha ^ { * } = 1 - \frac { e } { x - d }")
    out, report = sm.sanitize(doc, FakeKaTeX())
    assert report["wrapped"] == 0
    assert report["suppressed"] == 0
    assert report["kept"] == 1


def test_prose_and_structure_preserved():
    doc = _doc(r"a = & b")
    out, _ = sm.sanitize(doc, FakeKaTeX())
    assert "# Heading" in out
    assert "Some prose sentence that should always survive." in out
    assert "Closing prose sentence." in out


def test_cases_block_left_alone():
    doc = _doc(r"\begin{cases} a & b \\ c & d \end{cases}")
    out, report = sm.sanitize(doc, FakeKaTeX())
    assert report["wrapped"] == 0
    assert report["suppressed"] == 0
    assert r"\begin{cases}" in out


# --- fallback mode (no validator) --------------------------------------------

def test_fallback_wraps_alignment_and_suppresses_only_obvious_debris():
    doc = _doc(r"a = & b", "\\", r"^ { \prime } =")
    out, report = sm.sanitize(doc, None)
    assert report["mode"] == "heuristic"
    assert report["wrapped"] == 1          # the bare-& block
    assert report["suppressed"] == 1       # the lone backslash only
    assert r"^ { \prime } =" in out        # valid fragment kept even in fallback


def test_no_math_blocks_returns_unchanged():
    doc = "# Title\n\nJust prose, no math here.\n"
    out, report = sm.sanitize(doc, FakeKaTeX())
    assert out == doc
    assert report == {"mode": "heuristic", "wrapped": 0, "suppressed": 0, "kept": 0, "details": []}


# --- real KaTeX integration (skipped when unavailable) ------------------------

def test_real_katex_validation_when_available():
    validator = sm.KaTeXValidator(auto_install=False)
    if not validator.available:
        pytest.skip("KaTeX engine not reachable (no PDF_SKILL_KATEX / local cache)")
    doc = _doc(
        r"\frac { a } { b } = & \frac { c } { d }",   # bare & → should be wrapped & valid
        r"a = b \\ \intertext{x} c = d",              # \intertext → should be suppressed
        r"\alpha = 1 - \frac { e } { x }",            # valid → kept
    )
    out, report = sm.sanitize(doc, validator)
    assert report["mode"] == "katex"
    assert report["wrapped"] >= 1
    assert report["suppressed"] >= 1
    # Every surviving block must now actually render.
    survivors = re.findall(r"\$\$\n(.*?)\n\$\$", out, re.DOTALL)
    assert all(validator.validate_batch([s])[0] for s in survivors)
