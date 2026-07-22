"""Tests for strict Pydantic validation on input models.

Codex audit issue 3: input-side models (BuildSpec, EditOperation, etc.)
silently accepted misspelled fields and string-valued enums, so typos
like ``{"operation": "replcae"}`` parsed cleanly and then matched no
branch at runtime. The fixed models forbid extra fields and restrict
enum-like attributes to Literal values.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest


def test_edit_operation_rejects_unknown_operation():
    """EditOperation.operation must be one of 'replace', 'insert', 'delete'."""
    from models import EditOperation
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EditOperation(operation="replcae", paragraph_index=0,
                      old_text="foo", new_text="bar")


def test_edit_operation_rejects_unknown_field():
    """EditOperation must refuse extra fields, surfacing typos at parse time."""
    from models import EditOperation
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EditOperation(operation="replace", paragraph_index=0,
                      old_text="x", new_text="y", autor="me")


def test_edit_operation_accepts_three_valid_operations():
    """The three documented operations must continue to parse cleanly."""
    from models import EditOperation

    EditOperation(operation="replace", paragraph_index=0,
                  old_text="x", new_text="y")
    EditOperation(operation="insert", paragraph_index=0, new_text="y")
    EditOperation(operation="delete", paragraph_index=0, old_text="x")


def test_add_comment_spec_rejects_unknown_field():
    """AddCommentSpec must refuse typos like ``authour`` instead of ``author``."""
    from models import AddCommentSpec
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AddCommentSpec(mode="new", anchor_paragraph=0,
                       anchor_text="x", text="t", authour="Bob")


def test_internal_link_rejects_unknown_field():
    """InternalLink must refuse extra fields once required ones are present."""
    from models import InternalLink
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        InternalLink(anchor="a1", label="Chapter 1", color="red")


def test_buildspec_with_valid_fields_still_parses():
    """The forbid-extra config must not break legitimate specs."""
    from models import BuildSpec

    spec = BuildSpec(
        title="T",
        sections=[{"heading": "H", "paragraphs": ["p"]}],
        runtime="auto",
        page={"size": "letter", "orientation": "portrait"},
        columns=2,
        page_sections=[{
            "header": [{"type": "text", "value": "Top"}],
            "footer": [{"type": "page_number"}],
        }],
    )
    assert spec.title == "T"
    assert spec.columns == 2
    assert spec.page.size == "letter"
