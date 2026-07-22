"""Insert and replace a footnote in a copy of the synthetic input.docx.

Works entirely on a copy under pytest's tmp_path; the fixture is never mutated.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/core on sys.path so docx_support imports as a package (also set by
# conftest.py; repeated here so the module imports standalone).
_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parent.parent / "scripts" / "core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from docx_support.audit_ooxml import validate_docx  # noqa: E402
from docx_support.footnotes import (  # noqa: E402
    copy_docx,
    extract_footnotes,
    insert_footnote,
    replace_footnote_text,
)

import make_fixture  # noqa: E402

FIXTURE = _HERE / "input.docx"


def test_insert_and_replace_footnote(tmp_path):
    work = tmp_path / "work.docx"
    copy_docx(FIXTURE, work)
    assert work.exists()

    # Copy is structurally valid.
    assert not any(d.level == "error" for d in validate_docx(work))

    before = extract_footnotes(work)
    assert len(before) == 5

    # Insert a new footnote after a known anchor in the body text.
    anchor_idx = make_fixture.para_index_of(work, make_fixture.INSERT_ANCHOR)
    new_text = "See *Widget Test Source*, 99 J. Test 1 (2021) (synthetic insertion)."
    new_id = insert_footnote(
        work,
        paragraph_index=anchor_idx,
        text=new_text,
        after_text=make_fixture.INSERT_ANCHOR,
    )
    assert isinstance(new_id, int)

    after = extract_footnotes(work)
    assert len(after) == 6, f"expected 6 footnotes after insert, got {len(after)}"

    inserted = [f for f in after if f["footnote_id"] == new_id]
    assert len(inserted) == 1, f"new footnote id {new_id} not found"
    assert "Widget Test Source" in inserted[0]["text"]

    # Replace the new footnote's text.
    replacement = "Replaced synthetic footnote text after restyle."
    assert replace_footnote_text(work, new_id, replacement) is True

    replaced = extract_footnotes(work)
    target = [f for f in replaced if f["footnote_id"] == new_id]
    assert len(target) == 1
    assert "Replaced synthetic footnote text" in target[0]["text"]
    assert "Widget Test Source" not in target[0]["text"]

    # Document remains structurally valid after all edits.
    assert not any(d.level == "error" for d in validate_docx(work))
