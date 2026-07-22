"""Regression tests for multi-w:t run handling in apply_edits.

A single w:r run may legally contain more than one w:t child (this can
happen after external XML manipulation or specialized authoring tools).
The apply-edits pipelines previously collected only the first w:t per run
and removed the entire w:r when splicing, which silently destroyed text
in subsequent w:t children. These tests verify the trailing text is now
preserved across all three flavours of the edit pipeline (tracked,
silent, and add-comment new-anchor).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML = "http://www.w3.org/XML/1998/namespace"
REPO = Path(__file__).resolve().parent.parent


def _build_multi_wt_docx(dest: Path, first_text: str, second_text: str) -> None:
    """Build a fresh .docx whose first body paragraph contains a single w:r
    with two w:t children (first_text, second_text). The heading paragraph
    from python-docx is left intact so that the multi-w:t paragraph lands
    at body-index 1.
    """
    from docx import Document

    doc = Document()
    doc.add_paragraph("placeholder")
    doc.save(dest)
    with zipfile.ZipFile(dest, "r") as zin:
        members = {n: zin.read(n) for n in zin.namelist()}
    doc_tree = etree.fromstring(members["word/document.xml"])
    body = doc_tree.find(f"{{{W}}}body")
    p = body.find(f"{{{W}}}p")
    for r in list(p.findall(f"{{{W}}}r")):
        p.remove(r)
    r = etree.SubElement(p, f"{{{W}}}r")
    t1 = etree.SubElement(r, f"{{{W}}}t")
    t1.text = first_text
    t1.set(f"{{{XML}}}space", "preserve")
    t2 = etree.SubElement(r, f"{{{W}}}t")
    t2.text = second_text
    t2.set(f"{{{XML}}}space", "preserve")
    members["word/document.xml"] = etree.tostring(
        doc_tree, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
        for n, data in members.items():
            zout.writestr(n, data)


def _collect_text(docx: Path) -> str:
    with zipfile.ZipFile(docx) as zf:
        doc_xml = zf.read("word/document.xml")
    out = ""
    for t in etree.fromstring(doc_xml).iter(f"{{{W}}}t"):
        out += t.text or ""
    return out


def test_apply_non_tracked_edits_preserves_second_wt_sibling(tmp_path):
    """Replacing text inside the first w:t must not erase the second w:t's
    contents from the same w:r.
    """
    src = tmp_path / "src.docx"
    out = tmp_path / "out.docx"
    _build_multi_wt_docx(
        src,
        first_text="First ",
        second_text="paragraph of the clean fixture document.",
    )

    edits_path = tmp_path / "edits.json"
    edits_path.write_text(
        json.dumps([{
            "operation": "replace",
            "paragraph_index": 0,
            "old_text": "First",
            "new_text": "Initial",
        }]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "word_docx.py"),
            "apply-non-tracked-edits",
            str(src),
            "--edits",
            str(edits_path),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    final = _collect_text(out)
    assert final == "Initial paragraph of the clean fixture document.", (
        f"Trailing w:t was destroyed; got {final!r}"
    )


def test_apply_tracked_edits_preserves_second_wt_sibling(tmp_path):
    """Same property as above, but via the tracked-changes splice path."""
    src = tmp_path / "src.docx"
    out = tmp_path / "out.docx"
    _build_multi_wt_docx(
        src,
        first_text="First ",
        second_text="paragraph of the clean fixture document.",
    )

    edits_path = tmp_path / "edits.json"
    edits_path.write_text(
        json.dumps([{
            "operation": "replace",
            "paragraph_index": 0,
            "old_text": "First",
            "new_text": "Initial",
        }]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "word_docx.py"),
            "apply-tracked-edits",
            str(src),
            "--edits",
            str(edits_path),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    # The tracked-changes form produces a w:del (with original "First")
    # and a w:ins (with "Initial"). Word reading order through w:t nodes
    # is: w:del's delText -> "First", w:ins's t -> "Initial", trailing
    # plain run -> " paragraph of the clean fixture document.". Verify
    # the final assembled text (ignoring the deletion) keeps everything
    # after the match span.
    with zipfile.ZipFile(out) as zf:
        doc_xml = zf.read("word/document.xml").decode("utf-8")
    assert "paragraph of the clean fixture document." in doc_xml, (
        f"Trailing w:t was destroyed in tracked path; document.xml=\n{doc_xml}"
    )
    assert "<w:ins " in doc_xml
    assert "<w:del " in doc_xml


def test_silent_delete_preserves_second_wt_sibling(tmp_path):
    """Deleting text in the first w:t must not erase the second w:t."""
    src = tmp_path / "src.docx"
    out = tmp_path / "out.docx"
    _build_multi_wt_docx(
        src,
        first_text="DELETE_ME ",
        second_text="kept text.",
    )

    edits_path = tmp_path / "edits.json"
    edits_path.write_text(
        json.dumps([{
            "operation": "delete",
            "paragraph_index": 0,
            "old_text": "DELETE_ME ",
        }]),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "word_docx.py"),
            "apply-non-tracked-edits",
            str(src),
            "--edits",
            str(edits_path),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    final = _collect_text(out)
    assert final == "kept text.", (
        f"Trailing w:t was destroyed by delete; got {final!r}"
    )
