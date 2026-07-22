"""Regression tests for the post-build settings.xml zoom-percent patch.

python-docx writes ``<w:zoom w:val="bestFit"/>`` without the required
``w:percent`` attribute, so Anthropic's schema validator rejects every
python-routed build. The build path now post-processes settings.xml to
add ``w:percent="100"`` whenever the attribute is missing (codex audit
issue 5). The fix is applied centrally in build_docx so all callers
benefit; this test guards both the .docx-internal repair and the
validator's downstream acceptance.
"""

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from lxml import etree

REPO = Path(__file__).resolve().parent.parent
PLUGIN_BASE = Path.home() / ".claude" / "plugins" / "cache" / "anthropic-agent-skills" / "document-skills"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _build_simple(tmp_path: Path, spec_obj: dict | None = None) -> Path:
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(spec_obj or {"title": "Zoom Probe"}),
        encoding="utf-8",
    )
    out = tmp_path / "out.docx"
    result = subprocess.run(
        [
            sys.executable, str(REPO / "scripts" / "word_docx.py"),
            "build", "--spec", str(spec), "--out", str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"build failed: returncode={result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert out.is_file()
    return out


def _zoom_percent(docx: Path) -> str | None:
    with zipfile.ZipFile(docx) as zf:
        if "word/settings.xml" not in zf.namelist():
            return None
        settings = zf.read("word/settings.xml")
    tree = etree.fromstring(settings)
    zoom = tree.find(f"{{{W}}}zoom")
    if zoom is None:
        return None
    return zoom.get(f"{{{W}}}percent")


def test_python_build_writes_zoom_percent(tmp_path):
    """The python-routed build must set w:percent on the w:zoom element."""
    out = _build_simple(tmp_path)
    percent = _zoom_percent(out)
    assert percent is not None, (
        "w:percent attribute missing from settings.xml — Anthropic validator will reject this file"
    )
    assert percent.isdigit() and 10 <= int(percent) <= 500, (
        f"w:percent must be a sensible integer, got {percent!r}"
    )


def test_python_build_passes_validator(tmp_path):
    """The validator must accept a freshly built python-routed .docx end to end."""
    if not PLUGIN_BASE.is_dir():
        pytest.skip("Anthropic docx plugin not installed; cannot run validator")
    out = _build_simple(tmp_path)

    result = subprocess.run(
        [
            sys.executable, str(REPO / "scripts" / "word_docx.py"),
            "validate", str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "validate rejected a freshly built file:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )


def test_python_build_with_footnotes_still_has_zoom_percent(tmp_path):
    """Footnote injection rewrites the .docx; make sure the zoom fix survives."""
    spec = {
        "title": "With Footnotes",
        "sections": [{
            "heading": "Section",
            "paragraphs": ["See above.[^1]"],
        }],
        "footnotes": {"1": "Source citation."},
    }
    out = _build_simple(tmp_path, spec)
    percent = _zoom_percent(out)
    assert percent is not None, (
        "w:percent missing after footnote injection round-trip"
    )
