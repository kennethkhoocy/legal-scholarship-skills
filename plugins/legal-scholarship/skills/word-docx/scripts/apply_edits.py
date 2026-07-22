"""Paragraph-scoped tracked edits via direct OOXML manipulation.

Creates w:ins / w:del tracked-change markup in word/document.xml so that
the resulting .docx opens in Word with visible tracked changes, including
author and date metadata.

The core algorithm splits affected runs at match boundaries, preserving
text before and after the match in separate runs, then splices the
tracked-change elements in place between them. Only direct-child runs of
the paragraph are eligible; runs inside hyperlinks, content controls, or
existing tracked changes are treated as opaque boundaries.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from models import DiagnosticEntry, EditOperation

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"

_TRACKED_TAGS = frozenset((
    f"{{{W_NS}}}ins",
    f"{{{W_NS}}}del",
    f"{{{W_NS}}}moveTo",
    f"{{{W_NS}}}moveFrom",
    f"{{{W_NS}}}rPrChange",
    f"{{{W_NS}}}pPrChange",
    f"{{{W_NS}}}sectPrChange",
    f"{{{W_NS}}}tblPrChange",
    f"{{{W_NS}}}trPrChange",
    f"{{{W_NS}}}tcPrChange",
))


def _scan_max_id(tree: etree._Element) -> int:
    """Find the highest w:id value across all revision-bearing elements."""
    max_id = 0
    w_id = f"{{{W_NS}}}id"
    for el in tree.iter():
        val_str = el.get(w_id)
        if val_str is not None:
            try:
                max_id = max(max_id, int(val_str))
            except ValueError:
                pass
    return max_id


class _IdAllocator:
    def __init__(self, start: int):
        self._next = start

    def alloc(self) -> str:
        val = str(self._next)
        self._next += 1
        return val


def _resolve_date(op: EditOperation) -> str:
    if op.date:
        return op.date
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clone_rpr(run: etree._Element | None) -> etree._Element | None:
    if run is None:
        return None
    rpr = run.find(f"{{{W_NS}}}rPr")
    return deepcopy(rpr) if rpr is not None else None


def _make_run(text: str, rpr: etree._Element | None, tag: str = "t") -> etree._Element:
    r = etree.Element(f"{{{W_NS}}}r")
    if rpr is not None:
        r.append(deepcopy(rpr))
    t_el = etree.SubElement(r, f"{{{W_NS}}}{tag}")
    t_el.set(f"{{{XML_NS}}}space", "preserve")
    t_el.text = text
    return r


def _make_del(text: str, author: str, date: str, ids: _IdAllocator,
              rpr: etree._Element | None = None) -> etree._Element:
    el = etree.Element(f"{{{W_NS}}}del")
    el.set(f"{{{W_NS}}}id", ids.alloc())
    el.set(f"{{{W_NS}}}author", author)
    el.set(f"{{{W_NS}}}date", date)
    el.append(_make_run(text, rpr, tag="delText"))
    return el


def _make_ins(text: str, author: str, date: str, ids: _IdAllocator,
              rpr: etree._Element | None = None) -> etree._Element:
    el = etree.Element(f"{{{W_NS}}}ins")
    el.set(f"{{{W_NS}}}id", ids.alloc())
    el.set(f"{{{W_NS}}}author", author)
    el.set(f"{{{W_NS}}}date", date)
    el.append(_make_run(text, rpr, tag="t"))
    return el


def _is_inside_tracked(el: etree._Element) -> bool:
    """Return True if any ancestor of el is a tracked-change element."""
    parent = el.getparent()
    while parent is not None:
        if parent.tag in _TRACKED_TAGS:
            return True
        parent = parent.getparent()
    return False


def _run_has_non_text_content(run: etree._Element) -> bool:
    """Return True if the run contains non-text elements (tabs, breaks, drawings, fields)."""
    t_tag = f"{{{W_NS}}}t"
    rpr_tag = f"{{{W_NS}}}rPr"
    for child in run:
        if child.tag not in (t_tag, rpr_tag):
            return True
    return False


def _normalize_multi_wt_runs(para: etree._Element) -> None:
    """Split any direct-child run with multiple w:t children into separate
    single-w:t runs, preserving rPr formatting.

    A run of the form ``<w:r><w:rPr.../><w:t>A</w:t><w:t>B</w:t></w:r>`` is
    semantically identical to two consecutive runs each carrying the same
    rPr and one of the texts. Splitting them up front lets the splice
    machinery treat every editable text segment as a self-contained run,
    which prevents the trailing w:t in the original run from being
    destroyed when only the first w:t is matched (codex audit issue 1).

    Runs that contain non-text content (tabs, breaks, drawings, fields)
    are left untouched: their structural ordering matters and cannot be
    flattened safely. The existing diagnostic warning in apply_edits()
    already alerts callers to potential loss of such runs.
    """
    r_tag = f"{{{W_NS}}}r"
    t_tag = f"{{{W_NS}}}t"
    rpr_tag = f"{{{W_NS}}}rPr"

    for run in list(para):
        if run.tag != r_tag:
            continue
        if _is_inside_tracked(run):
            continue
        t_children = run.findall(t_tag)
        if len(t_children) <= 1:
            continue
        # Skip runs with non-text content: order with respect to tabs/
        # breaks/drawings is significant and cannot be flattened.
        if _run_has_non_text_content(run):
            continue

        rpr = run.find(rpr_tag)
        insert_idx = list(para).index(run)
        replacement_runs: list[etree._Element] = []
        for t_el in t_children:
            new_run = etree.Element(f"{{{W_NS}}}r")
            if rpr is not None:
                new_run.append(deepcopy(rpr))
            new_t = etree.SubElement(new_run, t_tag)
            xml_space = t_el.get(f"{{{XML_NS}}}space")
            if xml_space is not None:
                new_t.set(f"{{{XML_NS}}}space", xml_space)
            elif t_el.text and (
                t_el.text.startswith(" ") or t_el.text.endswith(" ")
            ):
                # Preserve leading/trailing whitespace explicitly so that
                # downstream consumers don't normalize it away.
                new_t.set(f"{{{XML_NS}}}space", "preserve")
            new_t.text = t_el.text or ""
            replacement_runs.append(new_run)

        para.remove(run)
        for offset, new_run in enumerate(replacement_runs):
            para.insert(insert_idx + offset, new_run)


def _get_direct_run_groups(para: etree._Element) -> list[list[tuple[etree._Element, etree._Element]]]:
    """Return groups of consecutive direct-child (run, t_element) pairs.

    Only collects runs that are immediate children of the w:p element.
    Runs inside hyperlinks, content controls, existing tracked changes,
    or other containers are excluded entirely.

    Non-run children (hyperlinks, bookmarks, tracked changes, etc.)
    act as opaque boundaries that break the group, preventing matches
    from spanning across them.

    Callers normalize multi-w:t runs via ``_normalize_multi_wt_runs``
    before invoking this helper, so each run is expected to carry at
    most one w:t child. A run with no w:t (or empty w:t) is treated as
    a group boundary.
    """
    r_tag = f"{{{W_NS}}}r"
    t_tag = f"{{{W_NS}}}t"
    groups: list[list[tuple[etree._Element, etree._Element]]] = []
    current: list[tuple[etree._Element, etree._Element]] = []

    for child in para:
        if child.tag == r_tag and not _is_inside_tracked(child):
            first_t = child.find(t_tag)
            if first_t is not None and first_t.text:
                current.append((child, first_t))
            else:
                # Run with no text is a boundary
                if current:
                    groups.append(current)
                    current = []
        else:
            # Non-run element is a boundary
            if current:
                groups.append(current)
                current = []

    if current:
        groups.append(current)
    return groups


def _find_in_group(group: list[tuple[etree._Element, etree._Element]],
                   target: str) -> list[tuple[etree._Element, etree._Element, str, str]] | None:
    """Find target text within a contiguous run group. Returns affected entries or None."""
    full_text = "".join(t.text for _, t in group)
    match_start = full_text.find(target)
    if match_start == -1:
        return None
    match_end = match_start + len(target)

    pos = 0
    affected = []
    for run, t_el in group:
        run_start = pos
        run_end = pos + len(t_el.text)
        pos = run_end

        if run_end <= match_start or run_start >= match_end:
            continue

        local_start = max(0, match_start - run_start)
        local_end = min(len(t_el.text), match_end - run_start)
        before_text = t_el.text[:local_start]
        after_text = t_el.text[local_end:]
        affected.append((run, t_el, before_text, after_text))

    return affected if affected else None


def _splice_replace(para: etree._Element, old_text: str, new_text: str,
                    author: str, date: str, ids: _IdAllocator) -> bool:
    """Find old_text within a contiguous run group, splice w:del + w:ins in place."""
    _normalize_multi_wt_runs(para)
    for group in _get_direct_run_groups(para):
        affected = _find_in_group(group, old_text)
        if affected is None:
            continue

        # Clone rPr from the first affected run directly (not double-wrapped)
        rpr = _clone_rpr(affected[0][0])

        replacements: list[etree._Element] = []
        if affected[0][2]:
            replacements.append(_make_run(affected[0][2], _clone_rpr(affected[0][0])))
        replacements.append(_make_del(old_text, author, date, ids, deepcopy(rpr) if rpr else None))
        replacements.append(_make_ins(new_text, author, date, ids, deepcopy(rpr) if rpr else None))
        if affected[-1][3]:
            replacements.append(_make_run(affected[-1][3], _clone_rpr(affected[-1][0])))

        insert_idx = list(para).index(affected[0][0])
        for run, _, _, _ in affected:
            para.remove(run)
        for i, elem in enumerate(replacements):
            para.insert(insert_idx + i, elem)

        return True

    return False


def _splice_delete(para: etree._Element, old_text: str,
                   author: str, date: str, ids: _IdAllocator) -> bool:
    """Find old_text within a contiguous run group, wrap in w:del in place."""
    _normalize_multi_wt_runs(para)
    for group in _get_direct_run_groups(para):
        affected = _find_in_group(group, old_text)
        if affected is None:
            continue

        rpr = _clone_rpr(affected[0][0])

        replacements: list[etree._Element] = []
        if affected[0][2]:
            replacements.append(_make_run(affected[0][2], _clone_rpr(affected[0][0])))
        replacements.append(_make_del(old_text, author, date, ids, deepcopy(rpr) if rpr else None))
        if affected[-1][3]:
            replacements.append(_make_run(affected[-1][3], _clone_rpr(affected[-1][0])))

        insert_idx = list(para).index(affected[0][0])
        for run, _, _, _ in affected:
            para.remove(run)
        for i, elem in enumerate(replacements):
            para.insert(insert_idx + i, elem)

        return True

    return False


def _apply_insert(para: etree._Element, new_text: str,
                  author: str, date: str, ids: _IdAllocator) -> bool:
    """Insert new_text as a tracked insertion at the end of the paragraph."""
    last_run = None
    r_tag = f"{{{W_NS}}}r"
    for child in para:
        if child.tag == r_tag and not _is_inside_tracked(child):
            last_run = child

    rpr = _clone_rpr(last_run)
    ins_el = _make_ins(new_text, author, date, ids, rpr)
    para.append(ins_el)
    return True


def apply_edits(
    input_path: Path,
    operations: list[EditOperation],
    output_path: Path,
) -> list[DiagnosticEntry]:
    """Apply tracked-change edits to a .docx via direct OOXML manipulation.

    Reads from input_path (never modified), writes to output_path.
    Uses atomic write via a temp file to prevent corruption on failure.
    """
    diags: list[DiagnosticEntry] = []
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Read from input — do NOT copy to output yet (prevents overwriting
    # an existing output on error before we've validated the input).
    try:
        with zipfile.ZipFile(input_path, "r") as zf:
            doc_xml = zf.read("word/document.xml")
            all_entries = {name: zf.read(name) for name in zf.namelist()}
    except Exception as exc:
        diags.append(DiagnosticEntry(
            level="error", source="apply_edits",
            message=f"Failed to read input: {exc}",
        ))
        return diags

    try:
        tree = etree.fromstring(doc_xml)
    except etree.XMLSyntaxError as exc:
        diags.append(DiagnosticEntry(
            level="error", source="apply_edits",
            message=f"Malformed document.xml: {exc}",
        ))
        return diags

    body = tree.find(f".//{{{W_NS}}}body")
    if body is None:
        diags.append(DiagnosticEntry(
            level="error", source="apply_edits",
            message="No w:body element found in document.xml.",
        ))
        return diags

    paragraphs = body.findall(f"{{{W_NS}}}p")

    # Start IDs above the highest existing ID in the entire document
    ids = _IdAllocator(_scan_max_id(tree) + 1)

    applied = 0
    for op in operations:
        date = _resolve_date(op)
        author = op.author or "LLM"

        if op.paragraph_index < 0 or op.paragraph_index >= len(paragraphs):
            diags.append(DiagnosticEntry(
                level="warning", source="apply_edits",
                message=(
                    f"paragraph_index {op.paragraph_index} out of range "
                    f"(document has {len(paragraphs)} body paragraphs). Skipping."
                ),
            ))
            continue

        para = paragraphs[op.paragraph_index]

        # Warn if any direct-child runs contain non-text content that could be lost
        r_tag = f"{{{W_NS}}}r"
        for child in para:
            if child.tag == r_tag and _run_has_non_text_content(child):
                diags.append(DiagnosticEntry(
                    level="warning", source="apply_edits",
                    message=(
                        f"Paragraph {op.paragraph_index} contains runs with non-text "
                        f"elements (tabs, breaks, drawings). These may be lost if "
                        f"the affected run is fully consumed by the edit."
                    ),
                ))
                break

        if op.operation == "replace":
            if not op.old_text or not op.new_text:
                diags.append(DiagnosticEntry(
                    level="warning", source="apply_edits",
                    message=f"Replace at paragraph {op.paragraph_index}: old_text and new_text required.",
                ))
                continue
            ok = _splice_replace(para, op.old_text, op.new_text, author, date, ids)
            if not ok:
                diags.append(DiagnosticEntry(
                    level="warning", source="apply_edits",
                    message=f"Replace at paragraph {op.paragraph_index}: old_text not found in direct runs.",
                ))
            else:
                applied += 1

        elif op.operation == "insert":
            if not op.new_text:
                diags.append(DiagnosticEntry(
                    level="warning", source="apply_edits",
                    message=f"Insert at paragraph {op.paragraph_index}: new_text required.",
                ))
                continue
            ok = _apply_insert(para, op.new_text, author, date, ids)
            if ok:
                applied += 1

        elif op.operation == "delete":
            if not op.old_text:
                diags.append(DiagnosticEntry(
                    level="warning", source="apply_edits",
                    message=f"Delete at paragraph {op.paragraph_index}: old_text required.",
                ))
                continue
            ok = _splice_delete(para, op.old_text, author, date, ids)
            if not ok:
                diags.append(DiagnosticEntry(
                    level="warning", source="apply_edits",
                    message=f"Delete at paragraph {op.paragraph_index}: old_text not found in direct runs.",
                ))
            else:
                applied += 1

        else:
            diags.append(DiagnosticEntry(
                level="warning", source="apply_edits",
                message=f"Unknown operation '{op.operation}' at paragraph {op.paragraph_index}.",
            ))

    # Atomic write: build in temp file, then replace output
    modified_xml = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True)
    all_entries["word/document.xml"] = modified_xml

    import os
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".docx", dir=output_path.parent)
    os.close(tmp_fd)
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in all_entries.items():
                zf.writestr(name, data)
        Path(tmp_path).replace(output_path)
    except Exception as exc:
        Path(tmp_path).unlink(missing_ok=True)
        diags.append(DiagnosticEntry(
            level="error", source="apply_edits",
            message=f"Failed to write output: {exc}",
        ))
        return diags

    diags.append(DiagnosticEntry(
        level="info", source="apply_edits",
        message=f"Applied {applied} of {len(operations)} edit(s) to {output_path.name}.",
    ))
    return diags


# ── Silent (non-tracked) edits ──────────────────────────────────────────


def _silent_splice_replace(para: etree._Element, old_text: str, new_text: str) -> bool:
    """Find old_text in a paragraph's runs, replace directly without tracked-change markup."""
    _normalize_multi_wt_runs(para)
    for group in _get_direct_run_groups(para):
        affected = _find_in_group(group, old_text)
        if affected is None:
            continue

        rpr = _clone_rpr(affected[0][0])

        replacements: list[etree._Element] = []
        if affected[0][2]:
            replacements.append(_make_run(affected[0][2], _clone_rpr(affected[0][0])))
        # Single plain run with new_text — no w:del or w:ins wrappers
        replacements.append(_make_run(new_text, deepcopy(rpr) if rpr else None))
        if affected[-1][3]:
            replacements.append(_make_run(affected[-1][3], _clone_rpr(affected[-1][0])))

        insert_idx = list(para).index(affected[0][0])
        for run, _, _, _ in affected:
            para.remove(run)
        for i, elem in enumerate(replacements):
            para.insert(insert_idx + i, elem)

        return True

    return False


def _silent_splice_delete(para: etree._Element, old_text: str) -> bool:
    """Find old_text in a paragraph's runs, remove it without tracked-change markup."""
    _normalize_multi_wt_runs(para)
    for group in _get_direct_run_groups(para):
        affected = _find_in_group(group, old_text)
        if affected is None:
            continue

        replacements: list[etree._Element] = []
        if affected[0][2]:
            replacements.append(_make_run(affected[0][2], _clone_rpr(affected[0][0])))
        # No w:del — simply omit the matched text
        if affected[-1][3]:
            replacements.append(_make_run(affected[-1][3], _clone_rpr(affected[-1][0])))

        insert_idx = list(para).index(affected[0][0])
        for run, _, _, _ in affected:
            para.remove(run)
        for i, elem in enumerate(replacements):
            para.insert(insert_idx + i, elem)

        return True

    return False


def _silent_apply_insert(para: etree._Element, new_text: str) -> bool:
    """Insert new_text as a plain run at the end of the paragraph (no w:ins wrapper)."""
    last_run = None
    r_tag = f"{{{W_NS}}}r"
    for child in para:
        if child.tag == r_tag and not _is_inside_tracked(child):
            last_run = child

    rpr = _clone_rpr(last_run)
    run = _make_run(new_text, rpr)
    para.append(run)
    return True


def apply_edits_silent(
    input_path: Path,
    operations: list[EditOperation],
    output_path: Path,
) -> list[DiagnosticEntry]:
    """Apply edits to a .docx without tracked-change markup.

    Behaves identically to apply_edits() in terms of paragraph indexing,
    run-splitting, error handling, and atomic ZIP write, but produces plain
    runs instead of w:del / w:ins elements.
    """
    diags: list[DiagnosticEntry] = []
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(input_path, "r") as zf:
            doc_xml = zf.read("word/document.xml")
            all_entries = {name: zf.read(name) for name in zf.namelist()}
    except Exception as exc:
        diags.append(DiagnosticEntry(
            level="error", source="apply_edits_silent",
            message=f"Failed to read input: {exc}",
        ))
        return diags

    try:
        tree = etree.fromstring(doc_xml)
    except etree.XMLSyntaxError as exc:
        diags.append(DiagnosticEntry(
            level="error", source="apply_edits_silent",
            message=f"Malformed document.xml: {exc}",
        ))
        return diags

    body = tree.find(f".//{{{W_NS}}}body")
    if body is None:
        diags.append(DiagnosticEntry(
            level="error", source="apply_edits_silent",
            message="No w:body element found in document.xml.",
        ))
        return diags

    paragraphs = body.findall(f"{{{W_NS}}}p")

    applied = 0
    for op in operations:
        if op.paragraph_index < 0 or op.paragraph_index >= len(paragraphs):
            diags.append(DiagnosticEntry(
                level="warning", source="apply_edits_silent",
                message=(
                    f"paragraph_index {op.paragraph_index} out of range "
                    f"(document has {len(paragraphs)} body paragraphs). Skipping."
                ),
            ))
            continue

        para = paragraphs[op.paragraph_index]

        r_tag = f"{{{W_NS}}}r"
        for child in para:
            if child.tag == r_tag and _run_has_non_text_content(child):
                diags.append(DiagnosticEntry(
                    level="warning", source="apply_edits_silent",
                    message=(
                        f"Paragraph {op.paragraph_index} contains runs with non-text "
                        f"elements (tabs, breaks, drawings). These may be lost if "
                        f"the affected run is fully consumed by the edit."
                    ),
                ))
                break

        if op.operation == "replace":
            if not op.old_text or not op.new_text:
                diags.append(DiagnosticEntry(
                    level="warning", source="apply_edits_silent",
                    message=f"Replace at paragraph {op.paragraph_index}: old_text and new_text required.",
                ))
                continue
            ok = _silent_splice_replace(para, op.old_text, op.new_text)
            if not ok:
                diags.append(DiagnosticEntry(
                    level="warning", source="apply_edits_silent",
                    message=f"Replace at paragraph {op.paragraph_index}: old_text not found in direct runs.",
                ))
            else:
                applied += 1

        elif op.operation == "insert":
            if not op.new_text:
                diags.append(DiagnosticEntry(
                    level="warning", source="apply_edits_silent",
                    message=f"Insert at paragraph {op.paragraph_index}: new_text required.",
                ))
                continue
            ok = _silent_apply_insert(para, op.new_text)
            if ok:
                applied += 1

        elif op.operation == "delete":
            if not op.old_text:
                diags.append(DiagnosticEntry(
                    level="warning", source="apply_edits_silent",
                    message=f"Delete at paragraph {op.paragraph_index}: old_text required.",
                ))
                continue
            ok = _silent_splice_delete(para, op.old_text)
            if not ok:
                diags.append(DiagnosticEntry(
                    level="warning", source="apply_edits_silent",
                    message=f"Delete at paragraph {op.paragraph_index}: old_text not found in direct runs.",
                ))
            else:
                applied += 1

        else:
            diags.append(DiagnosticEntry(
                level="warning", source="apply_edits_silent",
                message=f"Unknown operation '{op.operation}' at paragraph {op.paragraph_index}.",
            ))

    modified_xml = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True)
    all_entries["word/document.xml"] = modified_xml

    import os
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".docx", dir=output_path.parent)
    os.close(tmp_fd)
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in all_entries.items():
                zf.writestr(name, data)
        Path(tmp_path).replace(output_path)
    except Exception as exc:
        Path(tmp_path).unlink(missing_ok=True)
        diags.append(DiagnosticEntry(
            level="error", source="apply_edits_silent",
            message=f"Failed to write output: {exc}",
        ))
        return diags

    diags.append(DiagnosticEntry(
        level="info", source="apply_edits_silent",
        message=f"Applied {applied} of {len(operations)} silent edit(s) to {output_path.name}.",
    ))
    return diags
