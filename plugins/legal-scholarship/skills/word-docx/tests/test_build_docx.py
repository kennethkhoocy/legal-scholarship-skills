"""Test building a DOCX from the example response spec."""

import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest

from build_docx import build_from_spec
from models import BuildSpec

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
SPEC_PATH = EXAMPLES_DIR / "response_spec.example.json"


@pytest.fixture()
def example_spec() -> BuildSpec:
    """Load and parse the example response spec."""
    raw = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    return BuildSpec(**raw)


@pytest.fixture()
def tmp_dir():
    """Yield a temporary directory, cleaned up after the test."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


def test_example_spec_loads():
    """The example JSON should parse into a valid BuildSpec."""
    raw = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    spec = BuildSpec(**raw)
    assert spec.title == "Response to Reviewer Comments"
    assert len(spec.items) == 3
    assert len(spec.sections) == 1


def test_build_creates_file(example_spec, tmp_dir):
    """build_from_spec should produce a file that exists on disk."""
    out_path = tmp_dir / "output.docx"
    build_from_spec(example_spec, output_path=out_path)
    assert out_path.exists(), "Output .docx was not created"


def test_build_produces_valid_zip(example_spec, tmp_dir):
    """The output file should be a valid ZIP archive."""
    out_path = tmp_dir / "output.docx"
    build_from_spec(example_spec, output_path=out_path)
    assert zipfile.is_zipfile(out_path), "Output is not a valid ZIP file"


def test_build_contains_content_types(example_spec, tmp_dir):
    """The output .docx should contain [Content_Types].xml."""
    out_path = tmp_dir / "output.docx"
    build_from_spec(example_spec, output_path=out_path)
    with zipfile.ZipFile(out_path, "r") as zf:
        names = zf.namelist()
    assert "[Content_Types].xml" in names, (
        f"[Content_Types].xml missing from archive; found: {names}"
    )


def test_build_contains_document_xml(example_spec, tmp_dir):
    """The output .docx should contain word/document.xml."""
    out_path = tmp_dir / "output.docx"
    build_from_spec(example_spec, output_path=out_path)
    with zipfile.ZipFile(out_path, "r") as zf:
        names = zf.namelist()
    assert "word/document.xml" in names, (
        f"word/document.xml missing from archive; found: {names}"
    )


def test_build_with_footnotes(tmp_dir):
    """build should create footnotes from [^N] markers."""
    spec = BuildSpec(
        title="Test Document",
        sections=[{
            "heading": "Introduction",
            "paragraphs": ["This claim needs a citation.[^1] And another point.[^2]"],
        }],
        footnotes={"1": "See Smith (2020) at 15.", "2": "Compare Jones v. State."},
    )
    output = tmp_dir / "footnoted.docx"
    diags = build_from_spec(spec, output)
    assert output.exists()

    from lxml import etree

    with zipfile.ZipFile(output) as zf:
        # footnotes.xml must exist.
        assert "word/footnotes.xml" in zf.namelist()

        # Parse footnotes and verify user-defined entries.
        fn_xml = zf.read("word/footnotes.xml")
        tree = etree.fromstring(fn_xml)
        ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        footnotes = [
            fn for fn in tree.findall(f"{{{ns}}}footnote")
            if fn.get(f"{{{ns}}}id") not in ("-1", "0")
        ]
        assert len(footnotes) == 2

        # Verify the content type was added.
        ct_xml = etree.fromstring(zf.read("[Content_Types].xml"))
        ct_ns = ct_xml.nsmap.get(None, "")
        overrides = [
            o for o in ct_xml.findall(f"{{{ct_ns}}}Override")
            if o.get("PartName") == "/word/footnotes.xml"
        ]
        assert len(overrides) == 1

        # Verify the relationship was added.
        rels_xml = etree.fromstring(zf.read("word/_rels/document.xml.rels"))
        fn_rel_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"
        rels_ns = rels_xml.nsmap.get(None, "")
        fn_rels = [
            r for r in rels_xml.findall(f"{{{rels_ns}}}Relationship")
            if r.get("Type") == fn_rel_type
        ]
        assert len(fn_rels) == 1

        # Verify markers were removed from document text.
        doc_xml = zf.read("word/document.xml")
        assert b"[^1]" not in doc_xml
        assert b"[^2]" not in doc_xml

        # Verify footnoteReference elements exist in document.xml.
        doc_tree = etree.fromstring(doc_xml)
        refs = doc_tree.findall(f".//{{{ns}}}footnoteReference")
        assert len(refs) == 2


def test_build_without_footnotes_unchanged(tmp_dir):
    """build without footnotes should not create footnotes.xml."""
    spec = BuildSpec(
        title="Plain Document",
        sections=[{
            "heading": "Section",
            "paragraphs": ["No footnotes here."],
        }],
    )
    output = tmp_dir / "plain.docx"
    build_from_spec(spec, output)
    assert output.exists()

    with zipfile.ZipFile(output) as zf:
        assert "word/footnotes.xml" not in zf.namelist()
