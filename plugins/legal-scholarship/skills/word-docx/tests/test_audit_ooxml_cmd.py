"""Regression tests for the audit-ooxml CLI subcommand.

README.md and SKILL.md both advertise an ``audit-ooxml`` command, but
before codex audit issue 6 it was not registered with typer. Invoking
the documented command therefore returned ``No such command 'audit-ooxml'``.
The command is now wired through to ``audit_ooxml.audit_ooxml`` +
``write_audit``.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPT = REPO / "scripts" / "word_docx.py"


def _run_cli(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def test_audit_ooxml_help_lists_command():
    """The command must be discoverable through --help."""
    result = _run_cli("--help")
    assert result.returncode == 0
    assert "audit-ooxml" in result.stdout, (
        f"audit-ooxml absent from top-level --help; got:\n{result.stdout}"
    )


def test_audit_ooxml_subcommand_help_runs():
    """The subcommand-specific help must also work."""
    result = _run_cli("audit-ooxml", "--help")
    assert result.returncode == 0
    assert "audit" in result.stdout.lower(), (
        f"audit-ooxml --help did not include 'audit'; got:\n{result.stdout}"
    )


def test_audit_ooxml_writes_diagnostics_json(tmp_path):
    """Running the command on a real fixture must produce diagnostics.json."""
    out = tmp_path / "audit_out"
    result = _run_cli("audit-ooxml", str(FIXTURES / "clean.docx"), "--out", str(out))
    assert result.returncode == 0, result.stderr
    diag_path = out / "diagnostics.json"
    assert diag_path.is_file(), (
        f"diagnostics.json not written to {diag_path}; out_dir contents={list(out.iterdir()) if out.exists() else 'no dir'}"
    )
    # Sanity-check the payload structure.
    payload = json.loads(diag_path.read_text(encoding="utf-8"))
    assert "ooxml_audit" in payload
    audit = payload["ooxml_audit"]
    assert audit.get("valid") is True
    assert audit.get("file", "").endswith("clean.docx")


def test_audit_ooxml_reports_paragraph_count(tmp_path):
    """The audit payload must surface w:p counts pulled from document.xml."""
    out = tmp_path / "audit_with_revs"
    result = _run_cli(
        "audit-ooxml", str(FIXTURES / "with_revisions.docx"), "--out", str(out),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads((out / "diagnostics.json").read_text(encoding="utf-8"))
    counts = payload["ooxml_audit"].get("counts", {}).get("word/document.xml", {})
    assert counts.get("w:p", 0) >= 1, (
        f"Expected at least one w:p; got counts={counts!r}"
    )
