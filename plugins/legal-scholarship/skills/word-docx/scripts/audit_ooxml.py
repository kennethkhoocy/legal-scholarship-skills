"""Raw OOXML audit for .docx files.

Opens the .docx as a ZIP archive and inventories its parts, then counts
key Word ML elements (paragraphs, tables, comments, footnotes, endnotes,
insertions, deletions) across the principal XML parts.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

# Allow sibling imports when scripts/ is not a package.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from models import DiagnosticEntry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# Parts to inspect and elements to count within each.
_TARGETS: dict[str, list[str]] = {
    "word/document.xml": ["w:p", "w:tbl", "w:ins", "w:del"],
    "word/comments.xml": ["w:comment", "w:p"],
    "word/footnotes.xml": ["w:footnote", "w:p"],
    "word/endnotes.xml": ["w:endnote", "w:p"],
}

# Mapping from prefixed tag to lxml-compatible qualified name.
_QNAME: dict[str, str] = {
    "w:p": f"{{{_W_NS}}}p",
    "w:tbl": f"{{{_W_NS}}}tbl",
    "w:ins": f"{{{_W_NS}}}ins",
    "w:del": f"{{{_W_NS}}}del",
    "w:comment": f"{{{_W_NS}}}comment",
    "w:footnote": f"{{{_W_NS}}}footnote",
    "w:endnote": f"{{{_W_NS}}}endnote",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_docx(input_path: Path) -> list[DiagnosticEntry]:
    """Run basic structural checks on *input_path*.

    Returns a list of diagnostic entries. An empty list means the file
    passed all checks.
    """
    input_path = Path(input_path)
    diagnostics: list[DiagnosticEntry] = []

    if not input_path.exists():
        diagnostics.append(
            DiagnosticEntry(
                level="error",
                source="audit_ooxml.validate",
                message=f"File does not exist: {input_path}",
            )
        )
        return diagnostics

    if not zipfile.is_zipfile(input_path):
        diagnostics.append(
            DiagnosticEntry(
                level="error",
                source="audit_ooxml.validate",
                message=f"File is not a valid ZIP archive: {input_path.name}",
            )
        )
        return diagnostics

    try:
        with zipfile.ZipFile(input_path, "r") as zf:
            names = zf.namelist()
    except zipfile.BadZipFile as exc:
        diagnostics.append(
            DiagnosticEntry(
                level="error",
                source="audit_ooxml.validate",
                message=f"Cannot read ZIP: {exc}",
            )
        )
        return diagnostics

    for required in ("[Content_Types].xml", "word/document.xml"):
        if required not in names:
            diagnostics.append(
                DiagnosticEntry(
                    level="error",
                    source="audit_ooxml.validate",
                    message=f"Required part missing: {required}",
                )
            )

    return diagnostics


def audit_ooxml(input_path: Path) -> dict:
    """Audit the OOXML structure of *input_path*.

    Returns a dict with keys ``file``, ``valid``, ``parts``, and ``counts``.
    ``counts`` maps each examined part name to a dict of element tag counts.
    """
    input_path = Path(input_path)
    result: dict = {
        "file": str(input_path),
        "valid": False,
        "parts": [],
        "counts": {},
    }

    diags = validate_docx(input_path)
    has_errors = any(d.level == "error" for d in diags)
    if has_errors:
        return result

    try:
        from lxml import etree
    except ImportError:
        # Cannot count without lxml; return structure only.
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


def write_audit(
    audit_result: dict,
    diagnostics: list[DiagnosticEntry],
    out_dir: Path,
) -> None:
    """Write diagnostics.json combining *audit_result* and *diagnostics*."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "ooxml_audit": audit_result,
        "diagnostics": [d.model_dump() for d in diagnostics],
    }

    out_path = out_dir / "diagnostics.json"
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
