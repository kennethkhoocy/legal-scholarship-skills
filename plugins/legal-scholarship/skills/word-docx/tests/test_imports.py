"""Verify that all word-docx pipeline modules can be imported."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest


def test_import_models():
    import models

    assert hasattr(models, "BuildSpec")
    assert hasattr(models, "Comment")
    assert hasattr(models, "Revision")
    assert hasattr(models, "ParagraphRecord")
    assert hasattr(models, "EditOperation")
    assert hasattr(models, "Manifest")
    assert hasattr(models, "Section")
    assert hasattr(models, "ResponseItem")
    assert hasattr(models, "DiagnosticEntry")


def test_import_extract_comments():
    import extract_comments

    assert hasattr(extract_comments, "extract_comments")
    assert hasattr(extract_comments, "comments_to_markdown")
    assert hasattr(extract_comments, "write_comments")


def test_import_extract_revisions():
    import extract_revisions


def test_import_extract_text():
    import extract_text


def test_import_build_docx():
    import build_docx


def test_import_audit_ooxml():
    import audit_ooxml


def test_import_render_pdf():
    import render_pdf


def test_import_word_docx():
    import word_docx


def test_import_apply_edits():
    import apply_edits

    assert hasattr(apply_edits, "apply_edits")


def test_typer_app():
    from word_docx import app

    assert app is not None
