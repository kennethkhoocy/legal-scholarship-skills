"""Pytest fixtures shared across the pdf skill's tests."""

from pathlib import Path

import pytest

from tests.fixtures import (
    make_complex_pdf,
    make_encrypted_pdf,
    make_formula_pdf,
    make_scanned_pdf,
    make_simple_pdf,
    make_tabular_pdf,
)


@pytest.fixture
def simple_pdf(tmp_path: Path) -> Path:
    return make_simple_pdf(tmp_path / "simple.pdf", num_pages=3)


@pytest.fixture
def formula_pdf(tmp_path: Path) -> Path:
    """Math-glyph-dense born-digital PDF. Skips if no math-capable TTF exists."""
    try:
        return make_formula_pdf(tmp_path / "formula.pdf", num_pages=3)
    except RuntimeError as e:
        pytest.skip(str(e))


@pytest.fixture
def tabular_pdf(tmp_path: Path) -> Path:
    return make_tabular_pdf(tmp_path / "tabular.pdf", num_pages=2)


@pytest.fixture
def complex_pdf(tmp_path: Path) -> Path:
    return make_complex_pdf(tmp_path / "complex.pdf", num_pages=2)


@pytest.fixture
def scanned_pdf(tmp_path: Path) -> Path:
    return make_scanned_pdf(tmp_path / "scanned.pdf", num_pages=2)


@pytest.fixture
def encrypted_pdf(tmp_path: Path) -> Path:
    return make_encrypted_pdf(tmp_path / "encrypted.pdf", password="secret")
