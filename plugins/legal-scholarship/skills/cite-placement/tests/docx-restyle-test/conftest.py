"""Pytest configuration for the docx-restyle fixture tests.

Ensures ``scripts/core`` (so ``docx_support`` imports as a package) and this
directory (so ``make_fixture`` imports) are on sys.path at collection time,
and builds the synthetic ``input.docx`` fixture once per session if absent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parent.parent / "scripts" / "core"

for _p in (str(_CORE), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import make_fixture  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _ensure_fixture():
    """Build the synthetic fixture before any test runs, if it is missing."""
    if not (_HERE / "input.docx").exists():
        make_fixture.build()
    yield
