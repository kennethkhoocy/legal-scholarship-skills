"""Raw OOXML validation for .docx files.

Opens the .docx as a ZIP archive and checks structural integrity, then
counts key Word ML elements (paragraphs, tables, footnotes, endnotes).

Imported from word-docx skill for standalone use.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from models import DiagnosticEntry

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_TARGETS: dict[str, list[str]] = {
    "word/document.xml": ["w:p", "w:tbl", "w:ins", "w:del"],
    "word/comments.xml": ["w:comment", "w:p"],
    "word/footnotes.xml": ["w:footnote", "w:p"],
    "word/endnotes.xml": ["w:endnote", "w:p"],
}

_QNAME: dict[str, str] = {
    "w:p": f"{{{_W_NS}}}p",
    "w:tbl": f"{{{_W_NS}}}tbl",
    "w:ins": f"{{{_W_NS}}}ins",
    "w:del": f"{{{_W_NS}}}del",
    "w:comment": f"{{{_W_NS}}}comment",
    "w:footnote": f"{{{_W_NS}}}footnote",
    "w:endnote": f"{{{_W_NS}}}endnote",
}


def validate_docx(input_path: Path) -> list[DiagnosticEntry]:
    """Run basic structural checks on *input_path*."""
    input_path = Path(input_path)
    diagnostics: list[DiagnosticEntry] = []

    if not input_path.exists():
        diagnostics.append(DiagnosticEntry(
            level="error", source="audit_ooxml.validate",
            message=f"File does not exist: {input_path}",
        ))
        return diagnostics

    if not zipfile.is_zipfile(input_path):
        diagnostics.append(DiagnosticEntry(
            level="error", source="audit_ooxml.validate",
            message=f"File is not a valid ZIP archive: {input_path.name}",
        ))
        return diagnostics

    try:
        with zipfile.ZipFile(input_path, "r") as zf:
            names = zf.namelist()
    except zipfile.BadZipFile as exc:
        diagnostics.append(DiagnosticEntry(
            level="error", source="audit_ooxml.validate",
            message=f"Cannot read ZIP: {exc}",
        ))
        return diagnostics

    for required in ("[Content_Types].xml", "word/document.xml"):
        if required not in names:
            diagnostics.append(DiagnosticEntry(
                level="error", source="audit_ooxml.validate",
                message=f"Required part missing: {required}",
            ))

    return diagnostics


def audit_ooxml(input_path: Path) -> dict:
    """Audit the OOXML structure of *input_path*.

    Returns a dict with keys ``file``, ``valid``, ``parts``, and ``counts``.
    """
    input_path = Path(input_path)
    result: dict = {
        "file": str(input_path),
        "valid": False,
        "parts": [],
        "counts": {},
    }

    diags = validate_docx(input_path)
    if any(d.level == "error" for d in diags):
        return result

    try:
        from lxml import etree
    except ImportError:
        result["valid"] = True
        with zipfile.ZipFile(input_path, "r") as zf:
            result["parts"] = sorted(zf.namelist())
        return result

    with zipfile.ZipFile(input_path, "r") as zf:
        result["parts"] = sorted(zf.namelist())
        result["valid"] = True

        for part, tags in _TARGETS.items():
            if part not in zf.namelist():
                continue
            try:
                xml_bytes = zf.read(part)
                tree = etree.fromstring(xml_bytes)
            except Exception as exc:
                result["counts"][part] = {"_parse_error": str(exc)}
                if part == "word/document.xml":
                    result["valid"] = False
                continue

            tag_counts: dict[str, int] = {}
            for tag in tags:
                qname = _QNAME.get(tag)
                if qname is None:
                    continue
                tag_counts[tag] = len(list(tree.iter(qname)))
            result["counts"][part] = tag_counts

    return result
