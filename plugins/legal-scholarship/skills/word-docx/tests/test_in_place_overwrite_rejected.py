"""Regression tests for the in-place-overwrite guard.

SKILL.md's core principle forbids modifying source .docx files in place,
yet mutating CLI commands previously accepted the same path for input
and --out and silently destroyed the source (codex audit issue 4). The
guard in word_docx.py now rejects such invocations with exit code 1 for
every mutating command.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "word_docx.py"
PLUGIN_BASE = Path.home() / ".claude" / "plugins" / "cache" / "anthropic-agent-skills" / "document-skills"


def _run_cli(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def _stage_fixture(tmp_path: Path, name: str) -> Path:
    dest = tmp_path / name
    shutil.copy(FIXTURES / name, dest)
    return dest


def _assert_in_place_rejected(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 1, (
        f"In-place overwrite must exit 1; got returncode={result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    combined = (result.stdout + result.stderr).lower()
    assert "in-place" in combined, (
        f"Expected an 'in-place' error message; got:\n{result.stdout}\n{result.stderr}"
    )


def test_apply_edits_rejects_in_place_overwrite(tmp_path):
    src = _stage_fixture(tmp_path, "clean.docx")
    edits = tmp_path / "edits.json"
    edits.write_text('[{"operation":"replace","paragraph_index":1,"old_text":"First","new_text":"Initial"}]',
                     encoding="utf-8")

    before_size = src.stat().st_size
    result = _run_cli("apply-edits", str(src), "--edits", str(edits), "--out", str(src))
    _assert_in_place_rejected(result)
    assert src.stat().st_size == before_size, (
        "Source file size changed — the guard failed to prevent overwrite."
    )


def test_apply_tracked_edits_rejects_in_place_overwrite(tmp_path):
    src = _stage_fixture(tmp_path, "clean.docx")
    edits = tmp_path / "edits.json"
    edits.write_text('[{"operation":"replace","paragraph_index":1,"old_text":"First","new_text":"Initial"}]',
                     encoding="utf-8")

    result = _run_cli("apply-tracked-edits", str(src), "--edits", str(edits), "--out", str(src))
    _assert_in_place_rejected(result)


def test_apply_non_tracked_edits_rejects_in_place_overwrite(tmp_path):
    src = _stage_fixture(tmp_path, "clean.docx")
    edits = tmp_path / "edits.json"
    edits.write_text('[{"operation":"replace","paragraph_index":1,"old_text":"First","new_text":"Initial"}]',
                     encoding="utf-8")

    result = _run_cli("apply-non-tracked-edits", str(src), "--edits", str(edits), "--out", str(src))
    _assert_in_place_rejected(result)


def test_add_comment_rejects_in_place_overwrite(tmp_path):
    src = _stage_fixture(tmp_path, "clean.docx")
    result = _run_cli(
        "add-comment", str(src), "--out", str(src),
        "--anchor-paragraph", "1", "--anchor-text", "First paragraph",
        "--text", "comment",
    )
    _assert_in_place_rejected(result)


def test_accept_changes_rejects_in_place_overwrite(tmp_path):
    src = _stage_fixture(tmp_path, "with_revisions.docx")
    result = _run_cli("accept-changes", str(src), "--out", str(src))
    _assert_in_place_rejected(result)


def test_simplify_redlines_rejects_in_place_overwrite(tmp_path):
    src = _stage_fixture(tmp_path, "with_revisions.docx")
    result = _run_cli("simplify-redlines", str(src), "--out", str(src))
    _assert_in_place_rejected(result)


def test_apply_non_tracked_edits_distinct_paths_still_work(tmp_path):
    """Regression: the guard must not break the normal distinct-paths case."""
    src = _stage_fixture(tmp_path, "clean.docx")
    out = tmp_path / "out.docx"
    edits = tmp_path / "edits.json"
    edits.write_text('[{"operation":"replace","paragraph_index":1,"old_text":"First","new_text":"Initial"}]',
                     encoding="utf-8")

    result = _run_cli("apply-non-tracked-edits", str(src), "--edits", str(edits), "--out", str(out))
    assert result.returncode == 0, result.stderr
    assert out.is_file()
