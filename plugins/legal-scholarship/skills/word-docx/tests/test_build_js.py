# tests/test_build_js.py
"""Tests for the JS-routed build path (docx-js codegen)."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest


def _skip_unless_node_and_docx():
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    try:
        from node_bridge import ensure_docx_package

        ensure_docx_package()
    except Exception as e:
        pytest.skip(f"docx npm package not available: {e}")


def test_node_can_require_docx():
    _skip_unless_node_and_docx()


def test_codegen_emits_runnable_mjs(tmp_path):
    _skip_unless_node_and_docx()
    from build_js_codegen import emit_builder
    from models import BuildSpec

    spec = BuildSpec(
        title="JS Test",
        sections=[{"heading": "H", "paragraphs": ["Hello from JS"]}],
        toc={"title": "Contents", "heading_range": "1-3", "hyperlinks": True},
    )

    out_docx = tmp_path / "out.docx"
    mjs_path = tmp_path / "build.mjs"
    spec_path = tmp_path / "spec.json"
    emit_builder(spec, mjs_path, spec_path, out_docx)

    # Run the emitted script with node
    result = subprocess.run(["node", str(mjs_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert out_docx.is_file()
    assert out_docx.stat().st_size > 0


def test_build_command_routes_toc_to_js(tmp_path):
    _skip_unless_node_and_docx()
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps({
        "title": "JS Routed",
        "toc": {"title": "Contents", "heading_range": "1-3", "hyperlinks": True},
        "sections": [{"heading": "H1", "paragraphs": ["body"]}],
    }), encoding="utf-8")
    out_path = tmp_path / "out.docx"
    script = Path(__file__).resolve().parent.parent / "scripts" / "word_docx.py"
    result = subprocess.run(
        [sys.executable, str(script), "build", "--spec", str(spec_path), "--out", str(out_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out_path.is_file()
    assert out_path.stat().st_size > 0

    # Cheap sanity check: docx-js TOC produces something that mentions TOC or Contents
    import zipfile
    with zipfile.ZipFile(out_path, "r") as zf:
        doc_xml = zf.read("word/document.xml").decode("utf-8")
    assert ("TOC" in doc_xml) or ("TableOfContents" in doc_xml) or ("Contents" in doc_xml)


def test_build_runs_post_build_validate(tmp_path):
    """After a successful build, the validate command should be invoked on the output."""
    _skip_unless_node_and_docx()
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps({"title": "VAL"}), encoding="utf-8")
    out_path = tmp_path / "out.docx"
    script = Path(__file__).resolve().parent.parent / "scripts" / "word_docx.py"
    result = subprocess.run(
        [sys.executable, str(script), "build", "--spec", str(spec_path), "--out", str(out_path), "--verbose"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    # Verbose output should mention validation
    assert "validate" in (result.stdout + result.stderr).lower()


def test_js_internal_link_emits_bookmark_target(tmp_path):
    """Internal link anchored to 'appendix' should bookmark the section heading matching its label."""
    _skip_unless_node_and_docx()
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps({
        "title": "Linked",
        "sections": [
            {"heading": "Body", "paragraphs": ["See appendix"]},
            {"heading": "Appendix A", "paragraphs": ["Target content"]},
        ],
        "internal_links": [{"anchor": "appendix", "label": "Appendix A"}],
    }), encoding="utf-8")
    out_path = tmp_path / "out.docx"
    script = Path(__file__).resolve().parent.parent / "scripts" / "word_docx.py"
    result = subprocess.run(
        [sys.executable, str(script), "build", "--spec", str(spec_path), "--out", str(out_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    import zipfile
    with zipfile.ZipFile(out_path) as z:
        doc = z.read("word/document.xml").decode("utf-8")
    # Both the bookmark target and the hyperlink anchor must be present
    assert "bookmarkStart" in doc
    assert 'w:name="appendix"' in doc
    assert 'w:anchor="appendix"' in doc


def test_build_command_handles_missing_docx_package(tmp_path):
    """If ensure_docx_package raises, the CLI must exit cleanly with code 2 (not traceback).

    Regression test for the clean-error path in node_bridge.DocxPackageMissingError
    and its surfacing in word_docx.py.  This test is fully deterministic — it
    isolates the script root from any local ``node_modules/docx`` by copying the
    skill's ``scripts/`` tree into ``tmp_path/skill_copy/scripts/`` (so the
    script's resolved ``skill_root`` is ``tmp_path/skill_copy``, which has no
    node_modules), restricts PATH to a dir containing only ``node`` (so the
    ``npm root -g`` probe in node_bridge fails too), and runs from a cwd with
    no node_modules.  Any regression that suppresses the typed error or lets
    the traceback bubble up will fail this test.
    """
    import os
    import shutil as _shutil

    node_src = _shutil.which("node")
    if node_src is None:
        pytest.skip("node not installed")

    repo = Path(__file__).resolve().parent.parent
    fake_root = tmp_path / "skill_copy"
    _shutil.copytree(repo / "scripts", fake_root / "scripts")

    # Put a single `node` (and nothing else) in an isolated bin dir.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    node_dest = bin_dir / ("node.exe" if sys.platform == "win32" else "node")
    _shutil.copy2(node_src, node_dest)

    spec_path = tmp_path / "spec.json"
    out_path = tmp_path / "out.docx"
    spec_path.write_text(
        json.dumps({"title": "Needs JS", "toc": {"title": "Contents"}}),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env["PATH"] = str(bin_dir)
    # Empty NODE_PATH so node's module resolution can't find docx via env.
    empty_node_path = tmp_path / "empty_node_path"
    empty_node_path.mkdir()
    env["NODE_PATH"] = str(empty_node_path)
    # Strip npm-prefix env vars that would otherwise let node find globals.
    for key in ("npm_config_prefix", "npm_config_globalconfig", "npm_config_userconfig"):
        env.pop(key, None)
    # Ensure PYTHONPATH is not unintentionally inherited (it would let the test
    # process find local imports; we want sys.path to be derived from the
    # copied script's __file__).
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [
            sys.executable,
            str(fake_root / "scripts" / "word_docx.py"),
            "build",
            "--spec",
            str(spec_path),
            "--out",
            str(out_path),
        ],
        cwd=str(tmp_path),  # no node_modules anywhere along this path
        capture_output=True,
        text=True,
        env=env,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 2, (
        f"Expected exit 2 (DocxPackageMissingError), got {result.returncode}.\n"
        f"stdout={result.stdout!r}\n"
        f"stderr={result.stderr!r}"
    )
    assert "DocxPackageMissingError" in combined, (
        f"Expected 'DocxPackageMissingError' in output; got: {combined!r}"
    )
    # The error path should NOT surface a Python traceback to the user.
    assert "Traceback" not in combined, (
        f"Did not expect a Python traceback in the output; got: {combined!r}"
    )


def test_js_native_footnote_replaces_inline_marker(tmp_path):
    """Paragraph text with [^1] should produce a FootnoteReferenceRun, not literal [^1] text."""
    _skip_unless_node_and_docx()
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps({
        "title": "Footnoted",
        "sections": [{"heading": "Chapter", "paragraphs": ["Sentence with note[^1] inside."]}],
        "native_footnotes": {"1": "Footnote body text"},
    }), encoding="utf-8")
    out_path = tmp_path / "out.docx"
    script = Path(__file__).resolve().parent.parent / "scripts" / "word_docx.py"
    result = subprocess.run(
        [sys.executable, str(script), "build", "--spec", str(spec_path), "--out", str(out_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    import zipfile
    with zipfile.ZipFile(out_path) as z:
        doc = z.read("word/document.xml").decode("utf-8")
    # The literal [^1] should NOT appear in document.xml; a footnoteReference should
    assert "[^1]" not in doc
    assert "footnotereference" in doc.lower()


def test_bookmark_pairing_assertion_catches_duplicate_start_ids():
    """Sanity check that the bookmarkEnd pairing assertion in
    test_js_multiple_bookmarks_get_unique_ids actually has teeth.

    Regression test for codex audit issue 7: the previous formulation
    ``start_ids.count(eid) == 0`` was vacuous (membership implies count
    >= 1). The replacement asserts ``count(eid) == 1`` so duplicate
    bookmarkStart ids — which would corrupt the resulting OOXML — are
    flagged. This test constructs a synthetic ``start_ids`` / ``ends``
    pair that would slip past the old assertion and confirms the new
    formulation rejects it.
    """
    start_ids = ["1", "1", "2"]  # "1" duplicated — invalid OOXML
    ends = ["1", "2"]

    # Old (vacuous) check would have passed:
    old_orphan_ends = [eid for eid in ends if eid in start_ids and start_ids.count(eid) == 0]
    assert old_orphan_ends == [], (
        "Sanity: the old assertion was indeed vacuous on this input"
    )

    # New check should flag the duplicate:
    mismatched = [
        eid for eid in ends
        if eid in start_ids and start_ids.count(eid) != 1
    ]
    assert mismatched == ["1"], (
        f"Expected the new pairing check to flag '1'; got {mismatched}"
    )


def test_js_multiple_bookmarks_get_unique_ids(tmp_path):
    """A build with two internal links must produce well-formed bookmark + hyperlink OOXML.

    Regression test for unique numeric bookmark IDs.  Asserts:
      1. Each w:bookmarkStart has a unique w:id.
      2. Each w:bookmarkStart's w:id appears on a matching w:bookmarkEnd
         (so bookmarks are properly closed).
      3. Every w:hyperlink w:anchor="X" has a corresponding
         w:bookmarkStart w:name="X" (no dangling anchors).
    A revert to duplicate-id behavior, or to a build that emits hyperlinks
    pointing at non-existent bookmark names, will fail this test.
    """
    _skip_unless_node_and_docx()
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps({
        "title": "Multi-link",
        "sections": [
            {"heading": "Body", "paragraphs": ["See appendix A and B"]},
            {"heading": "Appendix A", "paragraphs": ["First appendix"]},
            {"heading": "Appendix B", "paragraphs": ["Second appendix"]},
        ],
        "internal_links": [
            {"anchor": "appendix-a", "label": "Appendix A"},
            {"anchor": "appendix-b", "label": "Appendix B"},
        ],
    }), encoding="utf-8")
    out_path = tmp_path / "out.docx"
    script = Path(__file__).resolve().parent.parent / "scripts" / "word_docx.py"
    result = subprocess.run(
        [sys.executable, str(script), "build", "--spec", str(spec_path), "--out", str(out_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    import re
    import zipfile
    with zipfile.ZipFile(out_path) as z:
        doc = z.read("word/document.xml").decode("utf-8")

    # ---- (1) Extract bookmarkStart (id, name) pairs and check uniqueness ----
    starts = re.findall(
        r'<w:bookmarkStart\b[^>]*\bw:id="(\d+)"[^>]*\bw:name="([^"]+)"',
        doc,
    )
    # Some emitters reverse the attribute order; pick those up too.
    starts += [
        (m.group(2), m.group(1))
        for m in re.finditer(
            r'<w:bookmarkStart\b[^>]*\bw:name="([^"]+)"[^>]*\bw:id="(\d+)"',
            doc,
        )
    ]
    # Deduplicate (the same bookmark could be picked up by both regexes)
    starts = list({(sid, sname) for sid, sname in starts})
    start_ids = [s[0] for s in starts]
    start_names = {s[1] for s in starts}
    assert len(start_ids) == len(set(start_ids)), (
        f"Duplicate bookmark IDs across bookmarkStart elements: {start_ids}"
    )
    # Both anchor names must be present.
    assert "appendix-a" in start_names, f"missing bookmark name 'appendix-a'; got {start_names}"
    assert "appendix-b" in start_names, f"missing bookmark name 'appendix-b'; got {start_names}"

    # ---- (2) Each bookmarkStart id must have a matching bookmarkEnd ----
    ends = re.findall(r'<w:bookmarkEnd\b[^>]*\bw:id="(\d+)"', doc)
    # Every Start id must appear in Ends.
    missing_ends = [sid for sid in start_ids if sid not in ends]
    assert not missing_ends, (
        f"bookmarkStart ids {missing_ends} have no matching bookmarkEnd; "
        f"start ids={start_ids} end ids={ends}"
    )
    # Symmetric check: every bookmarkEnd whose id matches one of our
    # internal-link starts must be paired with exactly one bookmarkStart of
    # that id (uniqueness on the start side was already established above,
    # but make the pairing explicit so a future regression that emits
    # multiple bookmarkStart elements for one anchor is caught here too).
    mismatched = [
        eid for eid in ends
        if eid in start_ids and start_ids.count(eid) != 1
    ]
    assert not mismatched, (
        f"bookmarkEnd ids paired with the wrong number of bookmarkStart ids: {mismatched}; "
        f"start ids={start_ids}"
    )

    # ---- (3) Every hyperlink anchor must point at a real bookmark name ----
    hyperlink_anchors = re.findall(r'<w:hyperlink\b[^>]*\bw:anchor="([^"]+)"', doc)
    # We requested two internal links — both anchors should appear.
    assert "appendix-a" in hyperlink_anchors, (
        f"missing hyperlink anchor 'appendix-a'; found {hyperlink_anchors}"
    )
    assert "appendix-b" in hyperlink_anchors, (
        f"missing hyperlink anchor 'appendix-b'; found {hyperlink_anchors}"
    )
    dangling = [a for a in hyperlink_anchors if a not in start_names]
    assert not dangling, (
        f"hyperlinks point at bookmark names that do not exist as bookmarkStart: "
        f"{dangling}; available bookmark names: {start_names}"
    )
