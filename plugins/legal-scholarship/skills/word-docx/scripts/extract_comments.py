"""Extract comments from .docx files using docx2python with OOXML audit.

Primary extraction uses docx2python to iterate over comments. A secondary
OOXML audit opens the underlying ZIP archive to count w:comment elements
in word/comments.xml, producing a diagnostic warning when the two counts
diverge.
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

# Allow sibling imports when scripts/ is not a package.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from models import Comment, DiagnosticEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"[^\S\n]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def _normalise(text: str) -> str:
    """Collapse runs of horizontal whitespace; preserve paragraph breaks."""
    text = _WS_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def _ooxml_comment_anchors(
    input_path: Path,
) -> tuple[list[dict], list[DiagnosticEntry]]:
    """Extract comment metadata and paragraph anchors from raw OOXML.

    Opens the ZIP archive and parses both word/comments.xml (for comment IDs,
    authors, dates, and text) and word/document.xml (for w:commentRangeStart
    elements that pin each comment to a specific paragraph).

    Returns a list of dicts, each with keys: ``id``, ``author``, ``date``,
    ``text``, and ``paragraph_index`` (None when the anchor is absent).
    """
    diags: list[DiagnosticEntry] = []
    anchors: list[dict] = []
    _ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ns = {"w": _ns}
    try:
        with zipfile.ZipFile(input_path, "r") as zf:
            names = zf.namelist()
            if "word/comments.xml" not in names:
                diags.append(
                    DiagnosticEntry(
                        level="info",
                        source="extract_comments.ooxml",
                        message="word/comments.xml not found in archive; document may have no comments.",
                    )
                )
                return [], diags

            from lxml import etree

            # --- Parse word/comments.xml for metadata ---
            xml_bytes = zf.read("word/comments.xml")
            tree = etree.fromstring(xml_bytes)
            comment_meta: dict[str, dict] = {}
            for comment_el in tree.findall(".//w:comment", ns):
                cid = comment_el.get(f"{{{_ns}}}id", "")
                if not cid:
                    continue
                # Gather all text inside the comment element.
                texts = [t.text or "" for t in comment_el.findall(".//w:t", ns)]
                comment_meta[cid] = {
                    "id": cid,
                    "author": comment_el.get(f"{{{_ns}}}author", ""),
                    "date": comment_el.get(f"{{{_ns}}}date", ""),
                    "text": " ".join(texts).strip(),
                    "paragraph_index": None,
                }

            # --- Parse word/document.xml for anchors ---
            if "word/document.xml" in names:
                try:
                    doc_bytes = zf.read("word/document.xml")
                    doc_tree = etree.fromstring(doc_bytes)

                    # Build a map from commentRangeStart id -> paragraph index.
                    # Walk all w:p elements in document order and check for
                    # w:commentRangeStart as a descendant of each paragraph.
                    body = doc_tree.find(".//w:body", ns)
                    if body is not None:
                        para_elements = body.findall("w:p", ns)
                        for p_idx, para in enumerate(para_elements):
                            # Primary: w:commentRangeStart
                            for crs in para.findall(
                                ".//w:commentRangeStart", ns
                            ):
                                anchor_id = crs.get(f"{{{_ns}}}id", "")
                                if anchor_id in comment_meta:
                                    comment_meta[anchor_id][
                                        "paragraph_index"
                                    ] = p_idx
                            # Fallback: w:commentReference inside w:r
                            for cr in para.findall(
                                ".//w:commentReference", ns
                            ):
                                ref_id = cr.get(f"{{{_ns}}}id", "")
                                if (
                                    ref_id in comment_meta
                                    and comment_meta[ref_id]["paragraph_index"] is None
                                ):
                                    comment_meta[ref_id][
                                        "paragraph_index"
                                    ] = p_idx

                        # Handle commentRangeStart that lives as a direct child
                        # of w:body (between paragraphs) rather than inside a
                        # w:p. Attribute it to the next paragraph.
                        prev_idx = 0
                        for child in body:
                            tag = etree.QName(child.tag).localname if child.tag else ""
                            if tag == "p":
                                prev_idx = list(body).index(child)
                            elif tag == "commentRangeStart":
                                anchor_id = child.get(f"{{{_ns}}}id", "")
                                if (
                                    anchor_id in comment_meta
                                    and comment_meta[anchor_id]["paragraph_index"]
                                    is None
                                ):
                                    # Find the next paragraph after this element.
                                    found_next = False
                                    for sibling in child.itersiblings():
                                        sib_tag = (
                                            etree.QName(sibling.tag).localname
                                            if sibling.tag
                                            else ""
                                        )
                                        if sib_tag == "p":
                                            sib_idx = list(body).index(sibling)
                                            # Map to that paragraph's index
                                            # within para_elements.
                                            for pi, pe in enumerate(
                                                para_elements
                                            ):
                                                if pe is sibling:
                                                    comment_meta[anchor_id][
                                                        "paragraph_index"
                                                    ] = pi
                                                    found_next = True
                                                    break
                                            break
                except Exception as anchor_exc:
                    diags.append(
                        DiagnosticEntry(
                            level="warning",
                            source="extract_comments.ooxml",
                            message=(
                                f"Anchor extraction from word/document.xml failed: "
                                f"{anchor_exc}; paragraph_index will be unavailable."
                            ),
                        )
                    )

            # Preserve insertion order from word/comments.xml.
            anchors = list(comment_meta.values())

    except zipfile.BadZipFile:
        diags.append(
            DiagnosticEntry(
                level="error",
                source="extract_comments.ooxml",
                message=f"Cannot open {input_path.name} as ZIP for OOXML audit.",
            )
        )
    except Exception as exc:
        diags.append(
            DiagnosticEntry(
                level="warning",
                source="extract_comments.ooxml",
                message=f"OOXML comment audit failed: {exc}",
            )
        )
    return anchors, diags


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_comments(input_path: Path) -> tuple[list[Comment], list[DiagnosticEntry]]:
    """Return (comments, diagnostics) extracted from *input_path*.

    Uses docx2python for structured extraction and cross-checks the count
    against raw OOXML.
    """
    input_path = Path(input_path)
    comments: list[Comment] = []
    diagnostics: list[DiagnosticEntry] = []

    # --- docx2python extraction ---
    try:
        from docx2python import docx2python

        with docx2python(str(input_path)) as docx:
            for idx, (ref_text, author, date, comment_text) in enumerate(
                docx.comments, start=1
            ):
                cid = f"C{idx:03d}"
                comments.append(
                    Comment(
                        comment_id=cid,
                        author=_normalise(str(author)),
                        date=str(date),
                        reference_text=_normalise(str(ref_text)),
                        comment_text=_normalise(str(comment_text)),
                        source="docx2python",
                    )
                )
    except ImportError:
        diagnostics.append(
            DiagnosticEntry(
                level="error",
                source="extract_comments",
                message="docx2python is not installed; cannot extract comments.",
            )
        )
        return comments, diagnostics
    except Exception as exc:
        diagnostics.append(
            DiagnosticEntry(
                level="error",
                source="extract_comments",
                message=f"docx2python extraction failed: {exc}",
            )
        )

    # --- OOXML cross-check, ID mapping, and anchor resolution ---
    ooxml_anchors, ooxml_diags = _ooxml_comment_anchors(input_path)
    diagnostics.extend(ooxml_diags)

    # Try matching by author+date first for a robust mapping that tolerates
    # ordering differences between docx2python and OOXML.  Fall back to
    # positional mapping when author+date matching leaves gaps.
    matched_indices: set[int] = set()
    for comment in comments:
        for ai, anchor in enumerate(ooxml_anchors):
            if ai in matched_indices:
                continue
            # Normalise author comparison (strip whitespace).
            anchor_author = (anchor.get("author") or "").strip()
            anchor_date = (anchor.get("date") or "").strip()
            if (
                anchor_author == comment.author.strip()
                and anchor_date == comment.date.strip()
            ):
                comment.ooxml_id = anchor["id"]
                comment.paragraph_index = anchor.get("paragraph_index")
                matched_indices.add(ai)
                break

    # Positional fallback for any comments that author+date didn't match.
    for i, anchor in enumerate(ooxml_anchors):
        if i in matched_indices:
            continue
        if i < len(comments) and comments[i].ooxml_id is None:
            comments[i].ooxml_id = anchor["id"]
            comments[i].paragraph_index = anchor.get("paragraph_index")
            matched_indices.add(i)

    if len(ooxml_anchors) != len(comments):
        diagnostics.append(
            DiagnosticEntry(
                level="warning",
                source="extract_comments",
                message=(
                    f"Comment count mismatch: docx2python extracted {len(comments)} "
                    f"but OOXML word/comments.xml contains {len(ooxml_anchors)} w:comment elements."
                ),
            )
        )

    return comments, diagnostics


def comments_to_markdown(comments: list[Comment]) -> str:
    """Render a list of comments as Markdown."""
    if not comments:
        return "# Comments\n\nNo comments found.\n"

    lines: list[str] = ["# Comments\n"]
    for c in comments:
        lines.append(f"## {c.comment_id} — {c.author} ({c.date})\n")
        if c.paragraph_index is not None:
            lines.append(f"**Paragraph index:** {c.paragraph_index}\n")
        lines.append(f"**Referenced text:** {c.reference_text}\n")
        lines.append(f"**Comment:** {c.comment_text}\n")
    return "\n".join(lines)


def write_comments(comments: list[Comment], out_dir: Path) -> None:
    """Write comments.json and comments.md into *out_dir*."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "comments.json"
    json_path.write_text(
        json.dumps(
            [c.model_dump() for c in comments],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    md_path = out_dir / "comments.md"
    md_path.write_text(comments_to_markdown(comments), encoding="utf-8")
