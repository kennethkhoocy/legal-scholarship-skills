"""Extract tracked changes (revisions) from .docx files.

Primary extraction uses docx-revisions (v0.1.5). When that library is
unavailable or raises an error, a fallback parser scans w:ins and w:del
elements in word/document.xml directly via lxml.
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

# Allow sibling imports when scripts/ is not a package.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from models import DiagnosticEntry, Revision


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


# ---------------------------------------------------------------------------
# Primary extractor — docx-revisions
# ---------------------------------------------------------------------------


def _extract_with_docx_revisions(
    input_path: Path,
) -> tuple[list[Revision], list[DiagnosticEntry]]:
    """Extract revisions using the docx-revisions library."""
    from docx_revisions import RevisionDocument

    revisions: list[Revision] = []
    diagnostics: list[DiagnosticEntry] = []

    try:
        doc = RevisionDocument(str(input_path))
    except Exception as exc:
        diagnostics.append(
            DiagnosticEntry(
                level="error",
                source="extract_revisions.docx_revisions",
                message=f"RevisionDocument failed to open file: {exc}",
            )
        )
        return revisions, diagnostics

    for idx, change in enumerate(doc.track_changes, start=1):
        rid = f"R{idx:03d}"
        type_name = type(change).__name__  # TrackedInsertion | TrackedDeletion
        rev_type = "insertion" if "Insertion" in type_name else "deletion"

        # Gather text.
        try:
            if hasattr(change, "text"):
                text = _normalise(str(change.text))
            else:
                # For deletions, iterate runs to assemble text.
                parts: list[str] = []
                for run in change.iter_runs():
                    run_text = getattr(run, "text", None)
                    if run_text:
                        parts.append(str(run_text))
                text = _normalise(" ".join(parts))
        except Exception as exc:
            text = ""
            diagnostics.append(
                DiagnosticEntry(
                    level="warning",
                    source="extract_revisions.docx_revisions",
                    message=f"Could not extract text for revision {rid}: {exc}",
                )
            )

        author = getattr(change, "author", "") or ""
        date = getattr(change, "date", "") or ""

        revisions.append(
            Revision(
                revision_id=rid,
                type=rev_type,
                author=str(author),
                date=str(date),
                text=text,
                source="docx_revisions",
            )
        )

    return revisions, diagnostics


# ---------------------------------------------------------------------------
# Fallback extractor — raw OOXML
# ---------------------------------------------------------------------------

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _read_document_xml(
    input_path: Path,
) -> tuple[bytes | None, list[DiagnosticEntry]]:
    """Read word/document.xml from a .docx archive."""
    diagnostics: list[DiagnosticEntry] = []
    try:
        with zipfile.ZipFile(input_path, "r") as zf:
            if "word/document.xml" not in zf.namelist():
                diagnostics.append(
                    DiagnosticEntry(
                        level="error",
                        source="extract_revisions.ooxml",
                        message="word/document.xml not found in archive.",
                    )
                )
                return None, diagnostics
            return zf.read("word/document.xml"), diagnostics
    except FileNotFoundError:
        diagnostics.append(
            DiagnosticEntry(
                level="error",
                source="extract_revisions.ooxml",
                message=f"File not found: {input_path}",
            )
        )
        return None, diagnostics
    except (zipfile.BadZipFile, OSError) as exc:
        diagnostics.append(
            DiagnosticEntry(
                level="error",
                source="extract_revisions.ooxml",
                message=f"Cannot open {input_path.name}: {exc}",
            )
        )
        return None, diagnostics


def _extract_with_ooxml(
    input_path: Path,
) -> tuple[list[Revision], list[DiagnosticEntry]]:
    """Fallback: parse revisions from word/document.xml.

    Extracts: w:ins, w:del (inline), w:moveFrom/w:moveTo (inline),
    w:pPrChange (paragraph property changes), w:rPrChange (run property
    changes), and paragraph-mark deletions (w:del inside w:pPr/w:rPr).
    """
    from lxml import etree

    revisions: list[Revision] = []

    xml_bytes, diagnostics = _read_document_xml(input_path)
    if xml_bytes is None:
        return revisions, diagnostics

    try:
        tree = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        diagnostics.append(
            DiagnosticEntry(
                level="error",
                source="extract_revisions.ooxml",
                message=f"Malformed XML in word/document.xml: {exc}",
            )
        )
        return revisions, diagnostics

    ins_tag = f"{{{_W_NS}}}ins"
    del_tag = f"{{{_W_NS}}}del"
    move_from_tag = f"{{{_W_NS}}}moveFrom"
    move_to_tag = f"{{{_W_NS}}}moveTo"
    t_tag = f"{{{_W_NS}}}t"
    deltext_tag = f"{{{_W_NS}}}delText"
    p_tag = f"{{{_W_NS}}}p"
    ppr_tag = f"{{{_W_NS}}}pPr"
    rpr_tag = f"{{{_W_NS}}}rPr"
    ppr_change_tag = f"{{{_W_NS}}}pPrChange"
    rpr_change_tag = f"{{{_W_NS}}}rPrChange"

    w_author = f"{{{_W_NS}}}author"
    w_date = f"{{{_W_NS}}}date"

    idx = 0
    for p_idx, para in enumerate(tree.iter(p_tag)):

        # --- Paragraph-mark deletion (w:del inside w:pPr > w:rPr) ---
        ppr = para.find(ppr_tag)
        if ppr is not None:
            ppr_rpr = ppr.find(rpr_tag)
            if ppr_rpr is not None:
                for del_mark in ppr_rpr.findall(del_tag):
                    idx += 1
                    revisions.append(
                        Revision(
                            revision_id=f"R{idx:03d}",
                            type="paragraph_mark_deletion",
                            author=del_mark.get(w_author, ""),
                            date=del_mark.get(w_date, ""),
                            text="¶",
                            paragraph_index=p_idx,
                            location="pPr/rPr",
                            source="ooxml",
                        )
                    )

            # --- Paragraph property change (w:pPrChange) ---
            for ppc in ppr.findall(ppr_change_tag):
                idx += 1
                old_props = _summarise_ppr(ppc.find(ppr_tag))
                new_props = _summarise_ppr(ppr)
                revisions.append(
                    Revision(
                        revision_id=f"R{idx:03d}",
                        type="paragraph_property_change",
                        author=ppc.get(w_author, ""),
                        date=ppc.get(w_date, ""),
                        text=f"from [{old_props}] to [{new_props}]",
                        paragraph_index=p_idx,
                        location="pPr",
                        source="ooxml",
                    )
                )

        # --- Walk inline elements in document order ---
        for elem in para.iter():
            if elem.tag == ins_tag:
                idx += 1
                parts: list[str] = []
                for t_elem in elem.iter(t_tag):
                    if t_elem.text:
                        parts.append(t_elem.text)
                revisions.append(
                    Revision(
                        revision_id=f"R{idx:03d}",
                        type="insertion",
                        author=elem.get(w_author, ""),
                        date=elem.get(w_date, ""),
                        text=_normalise("".join(parts)),
                        paragraph_index=p_idx,
                        source="ooxml",
                    )
                )

            elif elem.tag == del_tag:
                # Skip paragraph-mark deletions (already handled above)
                parent = elem.getparent()
                if parent is not None and parent.tag == rpr_tag:
                    continue
                idx += 1
                parts = []
                for t_elem in elem.iter(deltext_tag):
                    if t_elem.text:
                        parts.append(t_elem.text)
                revisions.append(
                    Revision(
                        revision_id=f"R{idx:03d}",
                        type="deletion",
                        author=elem.get(w_author, ""),
                        date=elem.get(w_date, ""),
                        text=_normalise("".join(parts)),
                        paragraph_index=p_idx,
                        source="ooxml",
                    )
                )

            elif elem.tag == move_from_tag:
                # Inline moveFrom (MoveFromRun): content moved away
                if elem.getparent() is not None and elem.getparent().tag == rpr_tag:
                    continue
                idx += 1
                parts = []
                for t_elem in elem.iter(t_tag):
                    if t_elem.text:
                        parts.append(t_elem.text)
                for t_elem in elem.iter(deltext_tag):
                    if t_elem.text:
                        parts.append(t_elem.text)
                revisions.append(
                    Revision(
                        revision_id=f"R{idx:03d}",
                        type="move_from",
                        author=elem.get(w_author, ""),
                        date=elem.get(w_date, ""),
                        text=_normalise("".join(parts)),
                        paragraph_index=p_idx,
                        source="ooxml",
                    )
                )

            elif elem.tag == move_to_tag:
                if elem.getparent() is not None and elem.getparent().tag == rpr_tag:
                    continue
                idx += 1
                parts = []
                for t_elem in elem.iter(t_tag):
                    if t_elem.text:
                        parts.append(t_elem.text)
                revisions.append(
                    Revision(
                        revision_id=f"R{idx:03d}",
                        type="move_to",
                        author=elem.get(w_author, ""),
                        date=elem.get(w_date, ""),
                        text=_normalise("".join(parts)),
                        paragraph_index=p_idx,
                        source="ooxml",
                    )
                )

            elif elem.tag == rpr_change_tag:
                idx += 1
                containing_rpr = elem.getparent()
                grandparent = containing_rpr.getparent() if containing_rpr is not None else None

                r_tag_full = f"{{{_W_NS}}}r"
                is_run_rpr = grandparent is not None and grandparent.tag == r_tag_full
                is_ppr_rpr = grandparent is not None and grandparent.tag == ppr_tag

                run_text = ""
                location = "rPr"
                if is_run_rpr:
                    t_parts = []
                    for t_elem in grandparent.findall(t_tag):
                        if t_elem.text:
                            t_parts.append(t_elem.text)
                    run_text = "".join(t_parts)
                elif is_ppr_rpr:
                    run_text = "¶"
                    location = "pPr/rPr"

                old_rpr = _summarise_rpr(elem.find(rpr_tag))
                new_rpr = _summarise_rpr(containing_rpr)
                revisions.append(
                    Revision(
                        revision_id=f"R{idx:03d}",
                        type="run_property_change",
                        author=elem.get(w_author, ""),
                        date=elem.get(w_date, ""),
                        text=f"'{run_text}' from [{old_rpr}] to [{new_rpr}]",
                        paragraph_index=p_idx,
                        location=location,
                        source="ooxml",
                    )
                )

    return revisions, diagnostics


def _summarise_ppr(ppr: "etree._Element | None") -> str:
    """Summarise paragraph properties as a compact string."""
    if ppr is None:
        return "default"
    props = []
    jc = ppr.find(f"{{{_W_NS}}}jc")
    if jc is not None:
        props.append(f"align={jc.get(f'{{{_W_NS}}}val', '?')}")
    ind = ppr.find(f"{{{_W_NS}}}ind")
    if ind is not None:
        parts = []
        for attr in ("left", "right", "firstLine", "hanging"):
            v = ind.get(f"{{{_W_NS}}}{attr}")
            if v:
                parts.append(f"{attr}={v}")
        if parts:
            props.append("ind(" + ",".join(parts) + ")")
    pstyle = ppr.find(f"{{{_W_NS}}}pStyle")
    if pstyle is not None:
        props.append(f"style={pstyle.get(f'{{{_W_NS}}}val', '?')}")
    numpr = ppr.find(f"{{{_W_NS}}}numPr")
    if numpr is not None:
        props.append("numbered")
    if not props:
        return "default"
    return "; ".join(props)


def _summarise_rpr(rpr: "etree._Element | None") -> str:
    """Summarise run properties as a compact string."""
    if rpr is None:
        return "default"
    props = []
    _ON_VALUES = (None, "", "true", "1", "on")
    simple_flags = ("b", "i", "strike", "dstrike", "smallCaps", "caps", "vanish")
    for flag in simple_flags:
        el = rpr.find(f"{{{_W_NS}}}{flag}")
        if el is not None:
            val = el.get(f"{{{_W_NS}}}val")
            if val in _ON_VALUES:
                props.append(flag)
    u_el = rpr.find(f"{{{_W_NS}}}u")
    if u_el is not None:
        u_val = u_el.get(f"{{{_W_NS}}}val", "single")
        if u_val and u_val != "none":
            props.append(f"u={u_val}" if u_val != "single" else "u")
    sz = rpr.find(f"{{{_W_NS}}}sz")
    if sz is not None:
        props.append(f"sz={sz.get(f'{{{_W_NS}}}val', '?')}")
    rfonts = rpr.find(f"{{{_W_NS}}}rFonts")
    if rfonts is not None:
        font = rfonts.get(f"{{{_W_NS}}}ascii") or rfonts.get(f"{{{_W_NS}}}hAnsi") or ""
        if font:
            props.append(f"font={font}")
    color = rpr.find(f"{{{_W_NS}}}color")
    if color is not None:
        props.append(f"color={color.get(f'{{{_W_NS}}}val', '?')}")
    if not props:
        return "default"
    return "; ".join(props)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_OOXML_ONLY_TYPES = frozenset((
    "move_from", "move_to",
    "paragraph_mark_deletion", "paragraph_property_change", "run_property_change",
))


def extract_revisions(
    input_path: Path,
) -> tuple[list[Revision], list[DiagnosticEntry]]:
    """Return (revisions, diagnostics) from *input_path*.

    Tries docx-revisions first for insertions/deletions; always
    supplements with the OOXML extractor for revision types that
    docx-revisions does not cover (moves, property changes, paragraph-
    mark deletions).
    """
    input_path = Path(input_path)
    diagnostics: list[DiagnosticEntry] = []
    primary_ok = False

    # Attempt primary extractor.
    try:
        revisions, diags = _extract_with_docx_revisions(input_path)
        diagnostics.extend(diags)
        if revisions or not diags:
            primary_ok = True
        # If primary returned zero revisions *and* reported errors, fall through.
    except ImportError:
        revisions = []
        diagnostics.append(
            DiagnosticEntry(
                level="warning",
                source="extract_revisions",
                message="docx-revisions not installed; falling back to raw OOXML parsing.",
            )
        )
    except Exception as exc:
        revisions = []
        diagnostics.append(
            DiagnosticEntry(
                level="warning",
                source="extract_revisions",
                message=f"docx-revisions raised {type(exc).__name__}: {exc}; falling back to OOXML.",
            )
        )

    if primary_ok:
        # Supplement: add OOXML-only types that docx-revisions doesn't cover
        ooxml_revisions, ooxml_diags = _extract_with_ooxml(input_path)
        diagnostics.extend(ooxml_diags)
        supplement = [r for r in ooxml_revisions if r.type in _OOXML_ONLY_TYPES]
        if supplement:
            next_idx = len(revisions)
            for r in supplement:
                next_idx += 1
                r.revision_id = f"R{next_idx:03d}"
            revisions.extend(supplement)
        return revisions, diagnostics

    # Full fallback: docx-revisions failed entirely
    revisions, ooxml_diags = _extract_with_ooxml(input_path)
    diagnostics.extend(ooxml_diags)
    return revisions, diagnostics


_TYPE_LABELS = {
    "insertion": "Insertion",
    "deletion": "Deletion",
    "move_from": "Move Source",
    "move_to": "Move Destination",
    "paragraph_mark_deletion": "Paragraph Mark Deletion",
    "paragraph_property_change": "Paragraph Property Change",
    "run_property_change": "Run Property Change",
}


def revisions_to_markdown(revisions: list[Revision]) -> str:
    """Render a list of revisions as Markdown."""
    if not revisions:
        return "# Tracked Changes\n\nNo tracked changes found.\n"

    lines: list[str] = ["# Tracked Changes\n"]
    for r in revisions:
        label = _TYPE_LABELS.get(r.type, r.type.replace("_", " ").title())
        lines.append(f"## {r.revision_id} — {label} by {r.author} ({r.date})\n")
        if r.paragraph_index is not None:
            lines.append(f"**Paragraph index:** {r.paragraph_index}\n")
        if r.location:
            lines.append(f"**Location:** {r.location}\n")
        lines.append(f"**Text:** {r.text}\n")
    return "\n".join(lines)


def write_revisions(revisions: list[Revision], out_dir: Path) -> None:
    """Write revisions.json and revisions.md into *out_dir*."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "revisions.json"
    json_path.write_text(
        json.dumps(
            [r.model_dump() for r in revisions],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    md_path = out_dir / "revisions.md"
    md_path.write_text(revisions_to_markdown(revisions), encoding="utf-8")
