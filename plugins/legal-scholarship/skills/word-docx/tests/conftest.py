"""Pytest configuration — generate fixtures on first run if missing."""

import subprocess
import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
REQUIRED = ("clean.docx", "with_comments.docx", "with_revisions.docx")


def pytest_configure(config):
    missing = [name for name in REQUIRED if not (FIXTURES_DIR / name).exists()]
    if missing:
        subprocess.run([sys.executable, str(FIXTURES_DIR / "build.py")], check=True)
