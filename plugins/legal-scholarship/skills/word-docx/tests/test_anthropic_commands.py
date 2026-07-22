"""End-to-end tests for commands that delegate to Anthropic's scripts."""

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PLUGIN_BASE = Path.home() / ".claude" / "plugins" / "cache" / "anthropic-agent-skills" / "document-skills"


def _skip_if_plugin_absent():
    if not PLUGIN_BASE.is_dir():
        pytest.skip("Anthropic docx plugin not installed")


def _run_cli(*args) -> subprocess.CompletedProcess:
    script = Path(__file__).resolve().parent.parent / "scripts" / "word_docx.py"
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
    )


def test_validate_command_runs_on_clean_fixture(tmp_path):
    _skip_if_plugin_absent()
    result = _run_cli("validate", str(FIXTURES / "clean.docx"))
    assert result.returncode == 0, result.stderr


def test_accept_changes_clears_revisions(tmp_path):
    _skip_if_plugin_absent()
    if sys.platform == "win32":
        pytest.skip("Anthropic's office/soffice.py uses socket.AF_UNIX (not available on Windows)")
    out = tmp_path / "accepted.docx"
    result = _run_cli("accept-changes", str(FIXTURES / "with_revisions.docx"), "--out", str(out))
    assert result.returncode == 0, result.stderr
    assert out.is_file()

    # Verify w:ins / w:del are gone
    import zipfile
    with zipfile.ZipFile(out, "r") as zf:
        doc_xml = zf.read("word/document.xml").decode("utf-8")
    assert "<w:ins " not in doc_xml
    assert "<w:del " not in doc_xml


def test_convert_doc_help_runs():
    """convert-doc help should print even if no .doc fixture exists."""
    _skip_if_plugin_absent()
    result = _run_cli("convert-doc", "--help")
    assert result.returncode == 0
    assert "convert" in result.stdout.lower()


def test_unpack_produces_document_xml(tmp_path):
    _skip_if_plugin_absent()
    out_dir = tmp_path / "unpacked"
    result = _run_cli("unpack", str(FIXTURES / "clean.docx"), "--out", str(out_dir))
    assert result.returncode == 0, result.stderr
    assert (out_dir / "word" / "document.xml").is_file()


def test_pack_roundtrip_through_unpack(tmp_path):
    """Unpack a fixture, repack it, verify the round-trip succeeds."""
    _skip_if_plugin_absent()
    unpacked = tmp_path / "unpacked"
    out = tmp_path / "repacked.docx"

    r1 = _run_cli("unpack", str(FIXTURES / "clean.docx"), "--out", str(unpacked))
    assert r1.returncode == 0, r1.stderr

    r2 = _run_cli("pack", str(unpacked), "--out", str(out), "--original", str(FIXTURES / "clean.docx"))
    assert r2.returncode == 0, r2.stderr
    assert out.is_file()


def test_simplify_redlines_runs_on_revisions_fixture(tmp_path):
    _skip_if_plugin_absent()
    out = tmp_path / "simplified.docx"
    result = _run_cli("simplify-redlines", str(FIXTURES / "with_revisions.docx"), "--out", str(out))
    assert result.returncode == 0, result.stderr
    assert out.is_file()


def test_docx_to_images_produces_at_least_one_page(tmp_path):
    _skip_if_plugin_absent()
    if sys.platform == "win32":
        pytest.skip("docx-to-images calls Anthropic's soffice.py which uses socket.AF_UNIX (not available on Windows)")
    if shutil.which("pdftoppm") is None:
        pytest.skip("pdftoppm (Poppler) not installed")
    out_dir = tmp_path / "pages"
    result = _run_cli("docx-to-images", str(FIXTURES / "clean.docx"), "--out-dir", str(out_dir))
    assert result.returncode == 0, result.stderr
    pages = list(out_dir.glob("page-*.jpg"))
    assert len(pages) >= 1
