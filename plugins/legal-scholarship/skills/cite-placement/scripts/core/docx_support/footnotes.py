"""Read and write footnotes in .docx files via direct OOXML manipulation.

python-docx has no native footnote API. This module operates on the raw XML
inside the .docx ZIP archive to:
  - Extract all footnote texts (for restyle / Phase 1 mapping)
  - Insert new footnotes at specified paragraph positions
  - Replace footnote content (for restyling)

Requires: lxml, python-docx (for paragraph iteration during extraction).
"""

from __future__ import annotations

import copy
import os
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

from lxml import etree

# ── OOXML namespaces ──────────────────────────────────────────────────────

_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
}

_W = _NS["w"]
_R = _NS["r"]


def _qn(tag: str) -> str:
    """Qualify a prefixed tag name (e.g., 'w:p' → '{http://...}p')."""
    prefix, local = tag.split(":")
    return f"{{{_NS[prefix]}}}{local}"


# ── Reading footnotes ─────────────────────────────────────────────────────


def _text_from_element(elem) -> str:
    """Recursively collect all w:t text from an element."""
    parts = []
    for node in elem.iter(_qn("w:t")):
        if node.text:
            parts.append(node.text)
    return "".join(parts)


def extract_footnotes(docx_path: Path) -> list[dict]:
    """Extract all footnotes from a .docx file.

    Returns a list of dicts with keys:
      - footnote_id (int): the OOXML footnote ID
      - text (str): plain text content of the footnote
      - paragraphs (list[str]): text of each paragraph in the footnote

    Footnotes with id 0 (separator) and -1 (continuation separator) are
    excluded.
    """
    docx_path = Path(docx_path)
    footnotes = []

    with zipfile.ZipFile(docx_path, "r") as zf:
        if "word/footnotes.xml" not in zf.namelist():
            return footnotes

        fn_xml = zf.read("word/footnotes.xml")
        tree = etree.fromstring(fn_xml)

        for fn_elem in tree.findall(_qn("w:footnote"), _NS):
            fn_id = int(fn_elem.get(_qn("w:id"), fn_elem.get("id", "-99")))
            fn_type = fn_elem.get(_qn("w:type"), fn_elem.get("type", ""))
            if fn_id <= 0 or fn_type in ("separator", "continuationSeparator"):
                continue

            paras = []
            for p in fn_elem.findall(_qn("w:p"), _NS):
                p_text = _text_from_element(p).strip()
                if p_text:
                    paras.append(p_text)

            footnotes.append({
                "footnote_id": fn_id,
                "text": " ".join(paras),
                "paragraphs": paras,
            })

    return footnotes


def extract_footnote_locations(docx_path: Path) -> list[dict]:
    """Map each footnote reference to its paragraph index in the document body.

    Returns a list of dicts with keys:
      - footnote_id (int)
      - paragraph_index (int): 0-based index among body paragraphs
      - paragraph_text (str): first 80 chars of the paragraph text
    """
    docx_path = Path(docx_path)
    locations = []

    with zipfile.ZipFile(docx_path, "r") as zf:
        doc_xml = zf.read("word/document.xml")
        tree = etree.fromstring(doc_xml)

    body = tree.find(_qn("w:body"), _NS)
    if body is None:
        return locations

    para_idx = 0
    for child in body:
        if child.tag != _qn("w:p"):
            continue

        p_text = _text_from_element(child).strip()

        for ref in child.iter(_qn("w:footnoteReference")):
            fn_id_str = ref.get(_qn("w:id"), ref.get("id", ""))
            if fn_id_str:
                fn_id = int(fn_id_str)
                if fn_id > 0:
                    locations.append({
                        "footnote_id": fn_id,
                        "paragraph_index": para_idx,
                        "paragraph_text": p_text[:80],
                    })

        para_idx += 1

    return locations


def build_display_number_map(docx_path: Path) -> dict:
    """Build a mapping from OOXML footnote ID to displayed footnote number.

    Scans footnote references in document order. References with
    customMarkFollows="1" (asterisk, dagger, etc.) are assigned their
    symbol character instead of a number. All other references are
    numbered sequentially starting from 1.

    Returns a dict with keys:
      - id_to_display (dict[int, str]): OOXML ID → displayed number/symbol
      - display_to_id (dict[str, int]): displayed number/symbol → OOXML ID
      - symbol_ids (list[int]): IDs that use custom marks (not numbered)
      - offset (int): number of symbol footnotes before the first numbered one
    """
    docx_path = Path(docx_path)

    with zipfile.ZipFile(docx_path, "r") as zf:
        doc_xml = zf.read("word/document.xml")

    tree = etree.fromstring(doc_xml)
    body = tree.find(_qn("w:body"), _NS)
    if body is None:
        return {"id_to_display": {}, "display_to_id": {}, "symbol_ids": [], "offset": 0}

    id_to_display = {}
    display_to_id = {}
    symbol_ids = []
    number_counter = 1

    for ref in body.iter(_qn("w:footnoteReference")):
        fn_id_str = ref.get(_qn("w:id"), ref.get("id", ""))
        if not fn_id_str:
            continue
        fn_id = int(fn_id_str)
        if fn_id <= 0:
            continue

        custom_mark = ref.get(_qn("w:customMarkFollows"), "")

        if custom_mark == "1":
            run = ref.getparent()
            sym = run.find(_qn("w:sym")) if run is not None else None
            if sym is not None:
                char_code = sym.get(_qn("w:char"), "")
                symbol_map = {"F02A": "*", "F020": "†", "F021": "‡", "F0A7": "§"}
                symbol = symbol_map.get(char_code, "*")
            else:
                symbol = "*"
            id_to_display[fn_id] = symbol
            display_to_id[symbol] = fn_id
            symbol_ids.append(fn_id)
        else:
            display_num = str(number_counter)
            id_to_display[fn_id] = display_num
            display_to_id[display_num] = fn_id
            number_counter += 1

    return {
        "id_to_display": id_to_display,
        "display_to_id": display_to_id,
        "symbol_ids": symbol_ids,
        "offset": len(symbol_ids),
    }


def _toggle_on(rPr, tag: str) -> bool:
    """Check if an OOXML toggle property is on (handles w:val="0"/"false"/"off")."""
    elem = rPr.find(_qn(tag))
    if elem is None:
        return False
    val = elem.get(_qn("w:val"), elem.get("val", ""))
    if val in ("0", "false", "off"):
        return False
    return True


def extract_footnotes_with_formatting(docx_path: Path) -> list[dict]:
    """Extract footnotes with run-level formatting information.

    Like extract_footnotes, but each footnote also includes a 'runs' list
    describing the formatting of each text segment:
      - text (str)
      - bold (bool)
      - italic (bool)
      - small_caps (bool)

    This enables the restyle pipeline to detect Bluebook small-caps
    book citations and preserve/convert formatting appropriately.
    """
    docx_path = Path(docx_path)
    footnotes = []

    with zipfile.ZipFile(docx_path, "r") as zf:
        if "word/footnotes.xml" not in zf.namelist():
            return footnotes
        fn_xml = zf.read("word/footnotes.xml")

    tree = etree.fromstring(fn_xml)

    for fn_elem in tree.findall(_qn("w:footnote"), _NS):
        fn_id = int(fn_elem.get(_qn("w:id"), fn_elem.get("id", "-99")))
        fn_type = fn_elem.get(_qn("w:type"), fn_elem.get("type", ""))
        if fn_id <= 0 or fn_type in ("separator", "continuationSeparator"):
            continue

        runs = []
        full_text_parts = []

        for p in fn_elem.findall(_qn("w:p"), _NS):
            for r in p.findall(_qn("w:r"), _NS):
                if r.find(_qn("w:footnoteRef")) is not None:
                    continue

                rPr = r.find(_qn("w:rPr"))
                is_bold = False
                is_italic = False
                is_small_caps = False

                if rPr is not None:
                    is_bold = _toggle_on(rPr, "w:b")
                    is_italic = _toggle_on(rPr, "w:i")
                    is_small_caps = _toggle_on(rPr, "w:smallCaps")

                text = "".join(
                    t.text for t in r.findall(_qn("w:t")) if t.text
                )
                if text:
                    runs.append({
                        "text": text,
                        "bold": is_bold,
                        "italic": is_italic,
                        "small_caps": is_small_caps,
                    })
                    full_text_parts.append(text)

        footnotes.append({
            "footnote_id": fn_id,
            "text": "".join(full_text_parts).strip(),
            "runs": runs,
        })

    return footnotes


# ── Writing footnotes ─────────────────────────────────────────────────────


def _next_footnote_id(fn_tree) -> int:
    """Find the next available footnote ID."""
    max_id = 0
    for fn in fn_tree.findall(_qn("w:footnote"), _NS):
        fn_id_str = fn.get(_qn("w:id"), fn.get("id", "0"))
        try:
            fid = int(fn_id_str)
            if fid > max_id:
                max_id = fid
        except ValueError:
            pass
    return max_id + 1


def _next_rid(rels_tree) -> str:
    """Find the next available relationship ID (rId)."""
    max_n = 0
    for rel in rels_tree.findall(".//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
        rid = rel.get("Id", "")
        m = re.match(r"rId(\d+)", rid)
        if m:
            n = int(m.group(1))
            if n > max_n:
                max_n = n
    return f"rId{max_n + 1}"


def _clone_rpr(run: etree._Element | None) -> etree._Element | None:
    """Clone the w:rPr from a run element, or return None if absent."""
    if run is None:
        return None
    rpr = run.find(_qn("w:rPr"))
    return copy.deepcopy(rpr) if rpr is not None else None


def _extract_base_rpr(fn_elem) -> etree._Element | None:
    """Extract the base run properties from an existing footnote's content runs.

    Scans paragraphs for the first content run (not the footnoteRef run) and
    clones its w:rPr. This captures font, size, color, and other properties
    so that replacement text preserves the original formatting.
    """
    for p in fn_elem.findall(_qn("w:p"), _NS):
        for r in p.findall(_qn("w:r"), _NS):
            if r.find(_qn("w:footnoteRef")) is not None:
                continue
            rpr = r.find(_qn("w:rPr"))
            if rpr is not None:
                base = copy.deepcopy(rpr)
                for toggle_tag in (_qn("w:b"), _qn("w:bCs"), _qn("w:i"),
                                   _qn("w:iCs"), _qn("w:smallCaps"),
                                   _qn("w:rStyle")):
                    el = base.find(toggle_tag)
                    if el is not None:
                        base.remove(el)
                return base
    return None


def _build_footnote_xml(fn_id: int, text: str, style: str = "FootnoteText",
                        base_rpr: etree._Element | None = None) -> etree._Element:
    """Build a w:footnote element with the given text.

    The text can contain basic formatting markers:
      - *italic text* → w:i run property
      - **bold text** → w:b run property
      - Plain text → normal run

    If base_rpr is provided, its properties (font, size, etc.) are applied
    to every content run, preserving the original footnote formatting.
    """
    fn = etree.SubElement(etree.Element("dummy"), _qn("w:footnote"))
    fn.set(_qn("w:id"), str(fn_id))

    p = etree.SubElement(fn, _qn("w:p"))

    pPr = etree.SubElement(p, _qn("w:pPr"))
    pStyle = etree.SubElement(pPr, _qn("w:pStyle"))
    pStyle.set(_qn("w:val"), style)

    ref_run = etree.SubElement(p, _qn("w:r"))
    ref_rPr = etree.SubElement(ref_run, _qn("w:rPr"))
    ref_style = etree.SubElement(ref_rPr, _qn("w:rStyle"))
    ref_style.set(_qn("w:val"), "FootnoteReference")
    etree.SubElement(ref_run, _qn("w:footnoteRef"))

    sep_run = etree.SubElement(p, _qn("w:r"))
    if base_rpr is not None:
        sep_run.append(copy.deepcopy(base_rpr))
    sep_t = etree.SubElement(sep_run, _qn("w:t"))
    sep_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    sep_t.text = " "

    _append_formatted_runs(p, text, base_rpr)

    return fn


def _append_formatted_runs(parent, text: str,
                           base_rpr: etree._Element | None = None):
    """Parse text with *italic*, **bold**, and ^^small caps^^ markers into w:r elements.

    If base_rpr is provided, each run inherits its properties (font, size,
    color, etc.). Format markers add w:i/w:b/w:smallCaps on top of the base.
    """
    segments = _parse_format_markers(text)
    for seg_text, bold, italic, small_caps in segments:
        if not seg_text:
            continue
        run = etree.SubElement(parent, _qn("w:r"))
        if base_rpr is not None or bold or italic or small_caps:
            rPr = copy.deepcopy(base_rpr) if base_rpr is not None else etree.SubElement(run, _qn("w:rPr"))
            if base_rpr is not None:
                run.insert(0, rPr)
            if bold:
                if rPr.find(_qn("w:b")) is None:
                    etree.SubElement(rPr, _qn("w:b"))
            if italic:
                if rPr.find(_qn("w:i")) is None:
                    etree.SubElement(rPr, _qn("w:i"))
            if small_caps:
                if rPr.find(_qn("w:smallCaps")) is None:
                    etree.SubElement(rPr, _qn("w:smallCaps"))
        t = etree.SubElement(run, _qn("w:t"))
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = seg_text


def _parse_format_markers(text: str) -> list[tuple[str, bool, bool, bool]]:
    """Parse *italic*, **bold**, and ^^small caps^^ markers.

    Returns (text, bold, italic, small_caps) tuples.
    """
    results = []
    i = 0
    current = []

    while i < len(text):
        if text[i:i + 2] == "^^":
            if current:
                results.append(("".join(current), False, False, False))
                current = []
            end = text.find("^^", i + 2)
            if end == -1:
                current.append("^^")
                i += 2
            else:
                results.append((text[i + 2:end], False, False, True))
                i = end + 2
        elif text[i:i + 2] == "**":
            if current:
                results.append(("".join(current), False, False, False))
                current = []
            end = text.find("**", i + 2)
            if end == -1:
                current.append("**")
                i += 2
            else:
                results.append((text[i + 2:end], True, False, False))
                i = end + 2
        elif text[i] == "*":
            if current:
                results.append(("".join(current), False, False, False))
                current = []
            end = text.find("*", i + 1)
            if end == -1:
                current.append("*")
                i += 1
            else:
                results.append((text[i + 1:end], False, True, False))
                i = end + 1
        else:
            current.append(text[i])
            i += 1

    if current:
        results.append(("".join(current), False, False, False))
    return results


def _ensure_footnotes_part(zf_path: Path):
    """Ensure the .docx has a word/footnotes.xml part and the relationship for it."""
    with zipfile.ZipFile(zf_path, "r") as zf:
        names = zf.namelist()

    if "word/footnotes.xml" in names:
        return

    fn_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
        '  <w:footnote w:type="separator" w:id="-1">\n'
        '    <w:p><w:r><w:separator/></w:r></w:p>\n'
        '  </w:footnote>\n'
        '  <w:footnote w:type="continuationSeparator" w:id="0">\n'
        '    <w:p><w:r><w:continuationSeparator/></w:r></w:p>\n'
        '  </w:footnote>\n'
        '</w:footnotes>'
    )

    # Build all three modifications, then write atomically
    rels_path = "word/_rels/document.xml.rels"
    replacements = {"word/footnotes.xml": fn_xml.encode("utf-8")}

    with zipfile.ZipFile(zf_path, "r") as zf:
        if rels_path in zf.namelist():
            rels_tree = etree.fromstring(zf.read(rels_path))
        else:
            rels_tree = etree.fromstring(
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
            )
        ct_tree = etree.fromstring(zf.read("[Content_Types].xml"))

    rid = _next_rid(rels_tree)
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    new_rel = etree.SubElement(rels_tree, f"{{{rel_ns}}}Relationship")
    new_rel.set("Id", rid)
    new_rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes")
    new_rel.set("Target", "footnotes.xml")
    replacements[rels_path] = etree.tostring(rels_tree, xml_declaration=True, encoding="UTF-8")

    ct_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
    override = etree.SubElement(ct_tree, f"{{{ct_ns}}}Override")
    override.set("PartName", "/word/footnotes.xml")
    override.set("ContentType", "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml")
    replacements["[Content_Types].xml"] = etree.tostring(ct_tree, xml_declaration=True, encoding="UTF-8")

    _atomic_replace_parts(zf_path, replacements)


def _replace_with_retry(src: Path, dst: Path, max_retries: int = 5):
    """Replace dst with src, retrying on PermissionError (Dropbox/antivirus locks)."""
    for attempt in range(max_retries):
        try:
            Path(src).replace(dst)
            return
        except PermissionError:
            if attempt == max_retries - 1:
                raise
            time.sleep(0.5 * (attempt + 1))


def _add_part_to_docx(docx_path: Path, part_name: str, data: bytes):
    """Add a new part to the .docx ZIP archive (atomic via temp file)."""
    fd, tmp_path = tempfile.mkstemp(suffix=".docx", dir=docx_path.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(docx_path, "r") as zf_in, zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf_out:
            for item in zf_in.infolist():
                zf_out.writestr(item, zf_in.read(item.filename))
            zf_out.writestr(part_name, data)
        _replace_with_retry(tmp_path, docx_path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _replace_part_in_docx(docx_path: Path, part_name: str, data: bytes):
    """Replace a part in the .docx ZIP archive (atomic via temp file)."""
    fd, tmp_path = tempfile.mkstemp(suffix=".docx", dir=docx_path.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(docx_path, "r") as zf_in, zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf_out:
            for item in zf_in.infolist():
                if item.filename == part_name:
                    zf_out.writestr(item, data)
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
            if part_name not in [i.filename for i in zf_in.infolist()]:
                zf_out.writestr(part_name, data)
        _replace_with_retry(tmp_path, docx_path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _atomic_replace_parts(docx_path: Path, replacements: dict[str, bytes]):
    """Replace multiple parts in the .docx ZIP in a single atomic write."""
    fd, tmp_path = tempfile.mkstemp(suffix=".docx", dir=docx_path.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(docx_path, "r") as zf_in, \
             zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf_out:
            for item in zf_in.infolist():
                if item.filename in replacements:
                    zf_out.writestr(item, replacements[item.filename])
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
            for name, data in replacements.items():
                if name not in [i.filename for i in zf_in.infolist()]:
                    zf_out.writestr(name, data)
        _replace_with_retry(tmp_path, docx_path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def insert_footnote(
    docx_path: Path,
    paragraph_index: int,
    text: str,
    after_text: str | None = None,
) -> int:
    """Insert a footnote into a .docx file at the given paragraph.

    Parameters
    ----------
    docx_path : Path
        Path to the .docx file (modified in place).
    paragraph_index : int
        0-based index of the target paragraph in the document body.
    text : str
        Footnote content. Supports *italic* and **bold** markers.
    after_text : str or None
        If provided, insert the footnote reference after this substring
        within the paragraph. If None, append at the end of the paragraph.

    Returns
    -------
    int
        The footnote ID that was assigned.
    """
    docx_path = Path(docx_path)
    _ensure_footnotes_part(docx_path)

    with zipfile.ZipFile(docx_path, "r") as zf:
        doc_xml = zf.read("word/document.xml")
        fn_xml = zf.read("word/footnotes.xml")

    doc_tree = etree.fromstring(doc_xml)
    fn_tree = etree.fromstring(fn_xml)

    fn_id = _next_footnote_id(fn_tree)

    fn_elem = _build_footnote_xml(fn_id, text)
    fn_tree.append(fn_elem)

    body = doc_tree.find(_qn("w:body"), _NS)
    paras = body.findall(_qn("w:p"), _NS)

    if paragraph_index >= len(paras):
        raise IndexError(f"paragraph_index {paragraph_index} out of range (document has {len(paras)} paragraphs)")

    target_para = paras[paragraph_index]

    ref_run = etree.Element(_qn("w:r"))
    ref_rPr = etree.SubElement(ref_run, _qn("w:rPr"))
    ref_style = etree.SubElement(ref_rPr, _qn("w:rStyle"))
    ref_style.set(_qn("w:val"), "FootnoteReference")
    fn_ref = etree.SubElement(ref_run, _qn("w:footnoteReference"))
    fn_ref.set(_qn("w:id"), str(fn_id))

    if after_text:
        _insert_ref_after_text(target_para, ref_run, after_text)
    else:
        target_para.append(ref_run)

    _atomic_replace_parts(docx_path, {
        "word/document.xml": etree.tostring(doc_tree, xml_declaration=True, encoding="UTF-8"),
        "word/footnotes.xml": etree.tostring(fn_tree, xml_declaration=True, encoding="UTF-8"),
    })

    return fn_id


def _insert_ref_after_text(para, ref_run, after_text: str):
    """Insert ref_run after the occurrence of after_text within the paragraph's runs."""
    runs = para.findall(_qn("w:r"), _NS)

    full_text = ""
    run_spans = []
    for run in runs:
        t_elems = run.findall(_qn("w:t"), _NS)
        run_text = "".join((t.text or "") for t in t_elems)
        start = len(full_text)
        full_text += run_text
        run_spans.append((run, start, len(full_text), t_elems))

    pos = full_text.find(after_text)
    if pos == -1:
        para.append(ref_run)
        return

    split_at = pos + len(after_text)

    for run, start, end, t_elems in run_spans:
        if start <= split_at <= end and split_at > start:
            if split_at == end:
                run.addnext(ref_run)
                return
            else:
                offset = split_at - start
                run_text = "".join((t.text or "") for t in t_elems)
                before = run_text[:offset]
                after = run_text[offset:]

                for t in t_elems:
                    t.text = ""
                if t_elems:
                    t_elems[0].text = before

                new_run = copy.deepcopy(run)
                new_t_elems = new_run.findall(_qn("w:t"), _NS)
                for t in new_t_elems:
                    t.text = ""
                if new_t_elems:
                    new_t_elems[0].text = after
                    new_t_elems[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

                run.addnext(ref_run)
                ref_run.addnext(new_run)
                return

    para.append(ref_run)


def replace_footnote_text(docx_path: Path, footnote_id: int, new_text: str) -> bool:
    """Replace the text content of a footnote by its ID.

    Preserves the original footnote's run properties (font, size, color,
    etc.) by extracting the base w:rPr from the first content run before
    rebuilding the paragraph.

    Returns True if the footnote was found and replaced, False otherwise.
    """
    docx_path = Path(docx_path)

    with zipfile.ZipFile(docx_path, "r") as zf:
        if "word/footnotes.xml" not in zf.namelist():
            return False
        fn_xml = zf.read("word/footnotes.xml")

    fn_tree = etree.fromstring(fn_xml)

    for fn_elem in fn_tree.findall(_qn("w:footnote"), _NS):
        fn_id_str = fn_elem.get(_qn("w:id"), fn_elem.get("id", ""))
        if fn_id_str == str(footnote_id):
            base_rpr = _extract_base_rpr(fn_elem)

            old_paras = list(fn_elem.findall(_qn("w:p"), _NS))
            pPr_source = None
            if old_paras:
                existing_pPr = old_paras[0].find(_qn("w:pPr"), _NS)
                if existing_pPr is not None:
                    pPr_source = copy.deepcopy(existing_pPr)

            for p in old_paras:
                fn_elem.remove(p)

            p = etree.SubElement(fn_elem, _qn("w:p"))
            if pPr_source is not None:
                p.insert(0, pPr_source)
            else:
                pPr = etree.SubElement(p, _qn("w:pPr"))
                pStyle = etree.SubElement(pPr, _qn("w:pStyle"))
                pStyle.set(_qn("w:val"), "FootnoteText")

            ref_run = etree.SubElement(p, _qn("w:r"))
            ref_rPr = etree.SubElement(ref_run, _qn("w:rPr"))
            ref_style = etree.SubElement(ref_rPr, _qn("w:rStyle"))
            ref_style.set(_qn("w:val"), "FootnoteReference")
            etree.SubElement(ref_run, _qn("w:footnoteRef"))

            sep_run = etree.SubElement(p, _qn("w:r"))
            if base_rpr is not None:
                sep_run.append(copy.deepcopy(base_rpr))
            sep_t = etree.SubElement(sep_run, _qn("w:t"))
            sep_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            sep_t.text = " "

            _append_formatted_runs(p, new_text, base_rpr)

            _replace_part_in_docx(docx_path, "word/footnotes.xml",
                                  etree.tostring(fn_tree, xml_declaration=True, encoding="UTF-8"))
            return True

    return False


def copy_docx(src: Path, dst: Path) -> Path:
    """Copy a .docx file to a new path (non-destructive pipeline start)."""
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst
