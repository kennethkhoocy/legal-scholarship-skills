"""Convert between LaTeX citation formatting and Word .docx footnotes.

This module bridges the citation pipeline (which formats citations as LaTeX
strings) and Word documents (which use OOXML footnotes with run-level
formatting). It handles:

  - Extracting a manuscript's content from .docx for Phase 1 mapping
  - Converting LaTeX-formatted citations to Word footnote runs
  - Building a .docx-compatible text representation from the pipeline output

The pipeline's planning phases (1–3) work on a text representation
of the manuscript; execution (Phase 5) either inserts \footnote{} into
.tex or calls the OOXML footnote insertion in this module.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .audit_ooxml import validate_docx
from .extract_text import extract_text
from .footnotes import (
    build_display_number_map,
    copy_docx,
    extract_footnote_locations,
    extract_footnotes,
    extract_footnotes_with_formatting,
    insert_footnote,
    replace_footnote_text,
)


def validate_and_extract(docx_path: Path, out_dir: Path) -> dict:
    """Validate a .docx file and extract its content for pipeline use.

    Returns a dict with:
      - valid (bool)
      - paragraphs_path (str): path to paragraphs.json
      - markdown_path (str): path to document.md
      - footnotes (list[dict]): extracted footnotes
      - footnote_locations (list[dict]): paragraph-level footnote mapping
      - diagnostics (list[dict])
    """
    docx_path = Path(docx_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    diags = validate_docx(docx_path)
    has_errors = any(d.level == "error" for d in diags)

    if has_errors:
        return {
            "valid": False,
            "diagnostics": [d.model_dump() for d in diags],
        }

    paragraphs, markdown, extract_diags = extract_text(docx_path)
    diags.extend(extract_diags)

    if any(d.level == "error" for d in extract_diags):
        return {
            "valid": False,
            "diagnostics": [d.model_dump() for d in diags],
        }

    from .extract_text import write_text
    write_text(paragraphs, markdown, out_dir)

    footnotes = extract_footnotes(docx_path)
    fn_locations = extract_footnote_locations(docx_path)

    fn_path = out_dir / "footnotes.json"
    fn_path.write_text(json.dumps(footnotes, indent=2, ensure_ascii=False), encoding="utf-8")

    fn_loc_path = out_dir / "footnote_locations.json"
    fn_loc_path.write_text(json.dumps(fn_locations, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "valid": True,
        "paragraphs_path": str(out_dir / "paragraphs.json"),
        "markdown_path": str(out_dir / "document.md"),
        "footnotes": footnotes,
        "footnote_locations": fn_locations,
        "diagnostics": [d.model_dump() for d in diags],
    }


def runs_to_marked_text(runs: list[dict]) -> str:
    """Convert run descriptors (from extract_footnotes_with_formatting) back to
    text with *italic*, **bold**, and ^^small_caps^^ markers.

    This produces text that replace_footnote_text can consume, preserving
    the formatting from the original footnote.
    """
    parts = []
    for r in runs:
        text = r["text"]
        if r.get("small_caps"):
            parts.append(f"^^{text}^^")
        elif r.get("bold"):
            parts.append(f"**{text}**")
        elif r.get("italic"):
            parts.append(f"*{text}*")
        else:
            parts.append(text)
    return "".join(parts)


def latex_footnote_to_plain(latex_text: str) -> str:
    r"""Convert LaTeX-formatted footnote text to plain text with *italic*/**bold** markers.

    The pipeline generates citations like:
      See Jeffrey N. Gordon, \textit{The Rise of Independent Directors}, 59
      \textsc{Stan.\ L.\ Rev.}\ 1465 (2007).

    This converts to:
      See Jeffrey N. Gordon, *The Rise of Independent Directors*, 59
      STAN. L. REV. 1465 (2007).

    Supports: \textit{}, \textbf{}, \textsc{}, \emph{}, thin spaces (\,),
    escaped spaces (\ ), and common LaTeX escaping.
    """
    text = latex_text

    text = re.sub(r"%CITE-PLACED\s*\n?", "", text)

    text = re.sub(r"\\textit\{([^}]*)\}", r"*\1*", text)
    text = re.sub(r"\\emph\{([^}]*)\}", r"*\1*", text)
    text = re.sub(r"\\textbf\{([^}]*)\}", r"**\1**", text)
    text = re.sub(r"\\textsc\{([^}]*)\}", lambda m: m.group(1).upper(), text)

    text = text.replace(r"\ ", " ")
    text = text.replace(r"\,", " ")
    text = text.replace(r"\&", "&")
    text = text.replace(r"\%", "%")
    text = text.replace(r"\$", "$")
    text = text.replace(r"\#", "#")
    text = text.replace(r"\{", "{")
    text = text.replace(r"\}", "}")
    text = text.replace("~", " ")

    text = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", text)

    text = re.sub(r"\s+", " ", text).strip()

    return text


def _append_plain_char(runs: list[dict], char: str):
    """Append a plain character to the last plain-text run, or start a new one."""
    if runs and not any(runs[-1].get(k) for k in ("bold", "italic", "small_caps")):
        runs[-1]["text"] += char
    else:
        runs.append({"text": char, "bold": False, "italic": False, "small_caps": False})


def latex_footnote_to_runs(latex_text: str) -> list[dict]:
    r"""Convert LaTeX-formatted footnote text to a list of run descriptors.

    Each run is a dict with keys:
      - text (str): the text content
      - bold (bool): whether this run is bold
      - italic (bool): whether this run is italic
      - small_caps (bool): whether this run uses small caps

    This provides finer-grained formatting than the *italic*/**bold** marker
    approach, preserving small caps for journal abbreviations.
    """
    text = re.sub(r"%CITE-PLACED\s*\n?", "", latex_text)

    runs = []
    i = 0

    while i < len(text):
        if text[i:].startswith("\\textit{"):
            content, end = _extract_brace_content(text, i + 8)
            runs.append({"text": _clean_latex(content), "bold": False, "italic": True, "small_caps": False})
            i = end
        elif text[i:].startswith("\\emph{"):
            content, end = _extract_brace_content(text, i + 6)
            runs.append({"text": _clean_latex(content), "bold": False, "italic": True, "small_caps": False})
            i = end
        elif text[i:].startswith("\\textbf{"):
            content, end = _extract_brace_content(text, i + 8)
            runs.append({"text": _clean_latex(content), "bold": True, "italic": False, "small_caps": False})
            i = end
        elif text[i:].startswith("\\textsc{"):
            content, end = _extract_brace_content(text, i + 8)
            runs.append({"text": _clean_latex(content), "bold": False, "italic": False, "small_caps": True})
            i = end
        elif text[i] == "\\" and i + 1 < len(text) and text[i + 1] in (" ", ","):
            _append_plain_char(runs, " ")
            i += 2
        elif text[i] == "\\" and i + 1 < len(text) and text[i + 1] in ("&", "%", "$", "#", "{", "}"):
            _append_plain_char(runs, text[i + 1])
            i += 2
        elif text[i] == "~":
            _append_plain_char(runs, " ")
            i += 1
        else:
            _append_plain_char(runs, text[i])
            i += 1

    return [r for r in runs if r["text"].strip() or r["text"] == " "]


def _extract_brace_content(text: str, start: int) -> tuple[str, int]:
    """Extract content between matched braces starting at position start."""
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[start:i - 1], i


def _clean_latex(text: str) -> str:
    """Remove common LaTeX escapes from text."""
    text = text.replace(r"\ ", " ")
    text = text.replace(r"\,", " ")
    text = text.replace(r"\&", "&")
    text = text.replace(r"\%", "%")
    text = text.replace("~", " ")
    return text
