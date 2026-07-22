"""Tests for the auto-router that decides between python and js build paths."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest


def _spec(**overrides):
    from models import BuildSpec

    base = {"title": "T", "sections": [], "items": []}
    base.update(overrides)
    return BuildSpec(**base)


def test_routing_simple_spec_picks_python():
    from build_docx import needs_js_runtime

    assert needs_js_runtime(_spec()) is False


def test_routing_toc_forces_js():
    from build_docx import needs_js_runtime

    spec = _spec(toc={"title": "Contents", "heading_range": "1-3", "hyperlinks": True})
    assert needs_js_runtime(spec) is True


def test_routing_multi_column_forces_js():
    from build_docx import needs_js_runtime

    assert needs_js_runtime(_spec(columns=2)) is True
    assert needs_js_runtime(_spec(columns=1)) is False


def test_routing_page_number_in_footer_forces_js():
    from build_docx import needs_js_runtime

    spec = _spec(page_sections=[{
        "header": [{"type": "text", "value": "H"}],
        "footer": [{"type": "text", "value": "Page "}, {"type": "page_number"}],
    }])
    assert needs_js_runtime(spec) is True


def test_routing_internal_links_force_js():
    from build_docx import needs_js_runtime

    spec = _spec(internal_links=[{"anchor": "c1", "label": "Chapter 1"}])
    assert needs_js_runtime(spec) is True


def test_routing_native_footnotes_force_js():
    from build_docx import needs_js_runtime

    spec = _spec(native_footnotes={"1": "Source"})
    assert needs_js_runtime(spec) is True


def test_routing_explicit_python_raises_on_js_features():
    from build_docx import BuildSpecRequiresJSError, decide_runtime

    spec = _spec(runtime="python", toc={"title": "C"})
    with pytest.raises(BuildSpecRequiresJSError):
        decide_runtime(spec)


def test_routing_explicit_js_overrides_simple_spec():
    from build_docx import decide_runtime

    assert decide_runtime(_spec(runtime="js")) == "js"


def test_routing_auto_simple_returns_python():
    from build_docx import decide_runtime

    assert decide_runtime(_spec(runtime="auto")) == "python"


def test_build_command_with_toc_spec_routes_to_js_or_errors_when_node_missing(tmp_path):
    """With node installed, toc specs should now succeed via the js path."""
    import shutil
    import subprocess

    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        '{"title":"T","toc":{"title":"Contents"}}',
        encoding="utf-8",
    )
    out_path = tmp_path / "out.docx"
    script = Path(__file__).resolve().parent.parent / "scripts" / "word_docx.py"
    result = subprocess.run(
        [sys.executable, str(script), "build", "--spec", str(spec_path), "--out", str(out_path)],
        capture_output=True,
        text=True,
    )
    if shutil.which("node") is None:
        assert result.returncode != 0
        assert "node" in (result.stderr + result.stdout).lower()
    else:
        assert result.returncode == 0, result.stderr
        assert out_path.is_file()


def test_build_command_python_path_still_works(tmp_path):
    """A simple spec with no js-only features must still produce a .docx."""
    import subprocess

    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        '{"title":"T","sections":[{"heading":"H","paragraphs":["p"]}]}',
        encoding="utf-8",
    )
    out_path = tmp_path / "out.docx"
    script = Path(__file__).resolve().parent.parent / "scripts" / "word_docx.py"
    result = subprocess.run(
        [sys.executable, str(script), "build", "--spec", str(spec_path), "--out", str(out_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out_path.is_file()


def test_buildspec_rejects_invalid_runtime():
    """BuildSpec should refuse runtime values outside the Literal set."""
    from models import BuildSpec
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BuildSpec(title="T", runtime="not-a-runtime")


def test_buildspec_rejects_unknown_field():
    """BuildSpec must refuse typo'd or unknown top-level fields (codex audit
    issue 3). Before the fix, ``{"runtmie": "js"}`` slipped through silently
    and the spec defaulted to runtime='auto' — masking user errors.
    """
    from models import BuildSpec
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BuildSpec(title="T", runtmie="js")


def test_page_config_rejects_invalid_size():
    """PageConfig.size must be limited to 'letter' or 'a4'."""
    from models import PageConfig
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PageConfig(size="tabloid")


def test_page_config_rejects_invalid_orientation():
    """PageConfig.orientation must be limited to 'portrait' or 'landscape'."""
    from models import PageConfig
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PageConfig(orientation="upside-down")


def test_page_section_element_rejects_invalid_type():
    """PageSectionElement.type must be limited to 'text' or 'page_number'."""
    from models import PageSectionElement
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PageSectionElement(type="image")


def test_python_path_honors_page_size_and_margins(tmp_path):
    import json
    import subprocess
    import zipfile

    spec = {
        "title": "T",
        "sections": [{"heading": "H", "paragraphs": ["p"]}],
        "page": {"size": "a4", "margins": {"top": 0.5, "bottom": 0.5, "left": 0.5, "right": 0.5}},
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    out_path = tmp_path / "out.docx"
    script = Path(__file__).resolve().parent.parent / "scripts" / "word_docx.py"
    result = subprocess.run(
        [sys.executable, str(script), "build", "--spec", str(spec_path), "--out", str(out_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    # Inspect word/document.xml for the correct page size
    with zipfile.ZipFile(out_path, "r") as zf:
        doc = zf.read("word/document.xml").decode("utf-8")
    # A4 portrait = 11906 x 16838 DXA
    assert 'w:w="11906"' in doc
    assert 'w:h="16838"' in doc
