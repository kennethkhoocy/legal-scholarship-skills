"""Standalone utility: restyle .docx footnotes from one citation style to another.

Uses the Anthropic Claude API for citation reformatting. This is an
alternative to the main pipeline (which is orchestrated by Claude Code
reading run_config.json and following phase-details.md).

Use this script when running outside Claude Code:
    python scripts/docx_restyle.py --config placement/run_config.json
"""

from __future__ import annotations

import os
import re
import json
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _DIR.parent
_CORE_DIR = _DIR / "core"
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

from docx_support.footnotes import (
    build_display_number_map,
    copy_docx,
    extract_footnotes_with_formatting,
    replace_footnote_text,
)
from docx_support.converter import runs_to_marked_text
from docx_support.audit_ooxml import validate_docx

# ── Style definitions ─────────────────────────────────────────────────────

STYLE_RULES = {
    "bluebook": {
        "has_signals": True,
        "id_term": "Id.",
        "supra_pattern": r"supra\s+note\s+(\d+)",
        "ampersand": "&",
        "et_al": "et al.",
        "trailing_period": True,
    },
    "oscola": {
        "has_signals": False,
        "id_term": "ibid",
        "cross_ref_template": "(n {n})",
        "ampersand": "and",
        "et_al": "and others",
        "trailing_period": False,
        "year_before_volume": True,
    },
    "chicago": {
        "has_signals": False,
        "id_term": "Ibid.",
        "cross_ref_template": None,  # uses shortened title
        "ampersand": "and",
        "et_al": "et al.",
        "trailing_period": True,
    },
    "apa": {
        "has_signals": False,
        "id_term": None,  # APA repeats author-year
        "cross_ref_template": None,
        "ampersand": "&",
        "et_al": "et al.",
        "trailing_period": True,
    },
    "mcgill": {
        "has_signals": True,
        "id_term": "Ibid",
        "supra_pattern": r"supra\s+note\s+(\d+)",
        "cross_ref_template": "supra note {n}",
        "ampersand": "and",
        "et_al": "et al.",
        "trailing_period": True,
    },
}

SIGNALS = [
    "See generally ", "See also ", "See e.g., ", "See, e.g., ",
    "See ", "But see ", "But cf. ", "Cf. ", "E.g., ", "Accord, ",
    "Compare ", "see generally ", "see also ", "see ",
    "but see ", "but cf. ", "cf. ", "e.g., ", "accord, ",
]

# ── Conversion helpers ────────────────────────────────────────────────────


def _remove_signals(text: str) -> str:
    for sig in SIGNALS:
        if text.startswith(sig):
            text = text[len(sig):]
            if text and text[0].islower():
                text = text[0].upper() + text[1:]
            break
    return text


def _split_citations(text: str) -> list[str]:
    parts, depth, current = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == ";" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


def _convert_id(text: str, source_rules: dict, target_rules: dict) -> tuple[str, bool]:
    """Convert ibid/Id. between styles. Returns (new_text, was_converted)."""
    src_id = source_rules["id_term"]
    tgt_id = target_rules["id_term"]
    if not src_id:
        return text, False

    stripped = text.strip()
    if stripped == src_id or stripped == src_id.rstrip("."):
        if tgt_id:
            return tgt_id, True
        return text, False

    at_match = re.match(rf"^{re.escape(src_id)}\s+at\s+(\d+)", stripped)
    if at_match:
        if tgt_id:
            return f"{tgt_id} {at_match.group(1)}", True
        return text, False

    return text, False


def _convert_supra(text: str, source_rules: dict, target_rules: dict,
                   display_map: dict | None = None) -> str:
    """Convert supra/cross-reference between styles."""
    src_pattern = source_rules.get("supra_pattern")
    if not src_pattern:
        return text

    tgt_template = target_rules.get("cross_ref_template")
    if not tgt_template:
        return text  # Target style doesn't use numbered cross-refs

    offset = display_map["offset"] if display_map else 0

    def _replace(m):
        note_num = int(m.group(1))
        if offset > 0 and display_map:
            displayed = display_map["id_to_display"].get(note_num, str(note_num - offset))
        else:
            displayed = str(note_num)
        return " " + tgt_template.format(n=displayed)

    text = re.sub(r",?\s*" + src_pattern + r"(?:\s*,\s*at\s+(\d+))?", _replace, text)
    return text


def _convert_ampersand(text: str, source_rules: dict, target_rules: dict) -> str:
    src = source_rules["ampersand"]
    tgt = target_rules["ampersand"]
    if src != tgt:
        text = re.sub(rf"\s+{re.escape(src)}\s+", f" {tgt} ", text)
    return text


def _convert_et_al(text: str, source_rules: dict, target_rules: dict) -> str:
    src = source_rules["et_al"]
    tgt = target_rules["et_al"]
    if src != tgt:
        text = text.replace(src, tgt)
    return text


def _remove_trailing_period(text: str) -> str:
    text = text.rstrip()
    if text.endswith(".") and not text.endswith(".."):
        if re.search(r"\)\s*\.$", text) or re.search(r"\d\.$", text):
            text = text[:-1]
        elif not re.search(r"\b[A-Z][a-z]{0,2}\.\s*$", text):
            text = text[:-1]
    return text


def _remove_month_from_year(text: str) -> str:
    months = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+"
    text = re.sub(rf"\({months}(\d{{4}})\)", r"(\1)", text)
    return text


def _rearrange_journal_cite(text: str) -> str:
    """Rearrange year placement for OSCOLA: (Year) Volume Journal Page."""
    m = re.search(r",\s+(\d+)\s+(.+?)\s+(\d+)\s+\(([^)]+\d{4}[^)]*)\)(.*)", text)
    if not m:
        return text
    volume, journal, page, year_info, trailing = m.groups()
    year_match = re.search(r"(\d{4}(?:[-–]\d{4})?)", year_info)
    if not year_match:
        return text
    year = year_match.group(1)
    prefix = text[:m.start()]
    result = f"{prefix}, ({year}) {volume} {journal.strip()} {page}"
    if trailing.strip():
        result += " " + trailing.strip()
    return result


def _convert_small_caps_to_target(marked_text: str, target_style: str) -> str:
    """Convert ^^small caps^^ markers based on target style."""
    if target_style == "oscola":
        # OSCOLA: book titles → italic, author names → plain
        parts = re.split(r"(\^\^.*?\^\^)", marked_text)
        result = []
        for part in parts:
            if part.startswith("^^") and part.endswith("^^"):
                content = part[2:-2]
                prev = "".join(result)
                if re.search(r"\bet al\.$", content) or re.search(r"^[A-Z][a-z]+ [A-Z]\.", content):
                    result.append(content)  # Author → plain
                else:
                    result.append(f"*{content}*")  # Title → italic
            else:
                result.append(part)
        return "".join(result)
    # Default: strip small caps markers
    return re.sub(r"\^\^(.*?)\^\^", r"\1", marked_text)


def _strip_markers(text: str) -> str:
    text = re.sub(r"\^\^(.*?)\^\^", r"\1", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    return text


# ── Classification ────────────────────────────────────────────────────────


def _classify(text: str, source_rules: dict, runs: list | None = None) -> str:
    text_stripped = text.strip()
    src_id = source_rules.get("id_term", "")

    if src_id and re.match(rf"^{re.escape(src_id)}\.?\s*$", text_stripped):
        return "id"
    if src_id and re.match(rf"^{re.escape(src_id)}\s+at\s+\d+", text_stripped):
        return "id_at"

    src_supra = source_rules.get("supra_pattern")
    if src_supra and re.search(src_supra, text_stripped) and len(text_stripped) < 200:
        if ";" in text_stripped:
            return "multi_with_supra"
        return "supra"

    if text_stripped.startswith("✉") or "@" in text_stripped[:50]:
        return "contact"

    has_year = bool(re.search(r"\d{4}", text_stripped))
    has_small_caps = runs and any(r.get("small_caps") for r in runs)
    has_publisher = bool(re.search(
        r"\((?:Oxford|Cambridge|Harvard|MIT|Yale|Princeton|Stanford|"
        r"University|Press|Publishers|Publishing|Elsevier|Springer|Wiley|"
        r"Transaction|Norton|McGraw|Pearson|Routledge|Sage|Kluwer|"
        r"West Academic|Foundation Press|Aspen)",
        text_stripped, re.IGNORECASE
    ))

    if not has_year and not has_small_caps and not has_publisher:
        return "discursive"
    if ";" in text_stripped:
        return "multi_cite"
    return "citation"


# ── Main conversion ──────────────────────────────────────────────────────


def _convert_one(text: str, fn_id: int, source_rules: dict, target_rules: dict,
                 runs: list | None, display_map: dict | None,
                 target_style: str) -> tuple[str, str]:
    """Convert a single footnote. Returns (new_text, action)."""
    # Build marked text from runs if available
    if runs:
        marked = runs_to_marked_text(runs)
        marked = _convert_small_caps_to_target(marked, target_style)
        plain = _strip_markers(marked)
    else:
        plain = text
        marked = None

    fn_type = _classify(plain, source_rules, runs=runs)

    if fn_type == "contact":
        return text, "skip_contact"
    if fn_type == "discursive":
        return text, "skip_discursive"

    if fn_type in ("id", "id_at"):
        new, converted = _convert_id(plain, source_rules, target_rules)
        if not target_rules.get("trailing_period", True):
            new = _remove_trailing_period(new)
        return new, "converted_id" if converted else "skip_discursive"

    # Work on plain text
    text = plain

    if fn_type == "supra":
        if not target_rules.get("has_signals", False):
            text = _remove_signals(text)
        text = _convert_ampersand(text, source_rules, target_rules)
        text = _convert_et_al(text, source_rules, target_rules)
        text = _convert_supra(text, source_rules, target_rules, display_map)

        # Handle trailing second citation after period
        period_parts = re.split(
            r"\.\s+(?=See |See also |But see |Cf\. |E\.g\., |[A-Z][a-z]+ [A-Z])",
            text, maxsplit=1
        )
        if len(period_parts) > 1:
            first = period_parts[0]
            second = period_parts[1]
            if not target_rules.get("has_signals", False):
                second = _remove_signals(second)
            second = _remove_month_from_year(second)
            if target_rules.get("year_before_volume"):
                second = _rearrange_journal_cite(second)
            second = _remove_trailing_period(second)
            text = first + "; " + second

        if not target_rules.get("trailing_period", True):
            text = _remove_trailing_period(text)
        text = re.sub(r",\s*\(n\s+", " (n ", text)
        return text, "converted_supra"

    # Full citations and multi-cites
    text = _remove_month_from_year(text)
    text = _convert_ampersand(text, source_rules, target_rules)
    text = _convert_et_al(text, source_rules, target_rules)

    if fn_type in ("multi_cite", "multi_with_supra"):
        parts = _split_citations(text)
        converted_parts = []
        for i, part in enumerate(parts):
            part = part.strip()
            if not target_rules.get("has_signals", False):
                part = _remove_signals(part)
            part = _convert_supra(part, source_rules, target_rules, display_map)
            part = re.sub(r",\s*\(n\s+", " (n ", part)
            if target_rules.get("year_before_volume"):
                part = _rearrange_journal_cite(part)
            part = _remove_trailing_period(part)
            converted_parts.append(part)
        text = "; ".join(converted_parts)
        if not target_rules.get("trailing_period", True):
            text = _remove_trailing_period(text)
        return text, "converted_multi"

    # Single citation
    if not target_rules.get("has_signals", False):
        text = _remove_signals(text)
    if target_rules.get("year_before_volume"):
        text = _rearrange_journal_cite(text)
    if not target_rules.get("trailing_period", True):
        text = _remove_trailing_period(text)
    return text, "converted_citation"


# ── LLM-based reformatting ────────────────────────────────────────────────


def _load_style_md(style_id: str) -> str:
    """Load the style .md file content for LLM context."""
    style_path = _SKILL_DIR / "references" / "styles" / f"{style_id}.md"
    if style_path.is_file():
        return style_path.read_text(encoding="utf-8")
    return f"(Style file not found: {style_path})"


def _build_llm_prompt(footnotes_batch: list[dict], current_style: str,
                      target_style: str, display_map: dict) -> str:
    """Build the LLM prompt for a batch of footnotes."""
    current_md = _load_style_md(current_style)
    target_md = _load_style_md(target_style)
    offset = display_map.get("offset", 0)

    fn_list = ""
    for fn in footnotes_batch:
        disp = display_map["id_to_display"].get(fn["footnote_id"], "?")
        fn_list += f"\n[FN {disp}] {fn['text']}\n"

    return f"""You are restyling footnote citations from {current_style.upper()} to {target_style.upper()}.

## Current citation style rules (for parsing input)
{current_md}

## Target citation style rules (for writing output)
{target_md}

## Footnote numbering
This document has {offset} symbol footnote(s) (e.g., asterisk) before the numbered footnotes.
Cross-references like "supra note N" in the original use OOXML IDs, not displayed numbers.
Subtract {offset} from each referenced number when converting to the target style's cross-reference format.

## Footnotes to restyle
{fn_list}

## Instructions
For each footnote above, output a JSON array where each element has:
- "display": the displayed footnote number (string)
- "new_text": the restyled footnote content in {target_style.upper()} format
- "skipped": true if the footnote should not be restyled (discursive notes, contact info, case citations, legislation)

Rules:
1. Parse each citation and reformat it according to the target style rules above.
2. Convert cross-references: supra note N → the target style's convention (e.g., (n N) for OSCOLA), adjusting the number by the offset.
3. Convert Id./ibid to the target style's equivalent.
4. Handle signals: remove them if the target style doesn't use signals.
5. Preserve discursive/non-citation content within footnotes unchanged.
6. For multi-citation footnotes (semicolon-separated), restyle each citation individually.
7. Do NOT add formatting markers — output plain text only.

Output ONLY the JSON array, no other text."""


def _call_llm(prompt: str) -> str:
    """Call the Anthropic Claude API."""
    import anthropic
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _parse_llm_response(response_text: str) -> list[dict]:
    """Parse the JSON array from the LLM response."""
    text = response_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


# ── Public API ────────────────────────────────────────────────────────────


BATCH_SIZE = 25


def restyle_docx(config: dict, progress_callback=None) -> dict:
    """Run the full .docx restyle pipeline using Claude API.

    Parameters
    ----------
    config : dict
        Run config with keys: input_tex, output_tex, current_style, target_style
    progress_callback : callable, optional
        Called with (message: str) for progress updates

    Returns
    -------
    dict with keys: output_path, total, changed, skipped, errors, changelog
    """
    input_path = Path(config["input_tex"])
    output_path = Path(config["output_tex"])
    current_style = config["current_style"]
    target_style = config["target_style"]

    def _log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg)

    # Step 1: Copy (non-destructive)
    copy_docx(input_path, output_path)
    _log(f"Copied to {output_path}")

    # Step 2: Validate
    diags = validate_docx(output_path)
    if any(d.level == "error" for d in diags):
        return {"output_path": str(output_path), "total": 0, "changed": 0,
                "skipped": 0, "errors": 1, "error_message": "Invalid .docx file",
                "changelog": []}

    # Step 3: Build display number map
    display_map = build_display_number_map(output_path)
    _log(f"Display offset: {display_map['offset']} symbol footnote(s)")

    # Step 4: Extract footnotes with formatting
    footnotes = extract_footnotes_with_formatting(output_path)
    _log(f"Extracted {len(footnotes)} footnotes")

    # Step 5: Check API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        _log("ERROR: ANTHROPIC_API_KEY not set. Cannot run LLM restyle.")
        return {"output_path": str(output_path), "total": len(footnotes),
                "changed": 0, "skipped": 0, "errors": 1,
                "error_message": "ANTHROPIC_API_KEY environment variable not set",
                "changelog": []}

    # Step 6: Send footnotes to Claude in batches
    changelog = []
    errors = 0
    changed = 0
    skipped = 0
    total_batches = (len(footnotes) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(footnotes))
        batch = footnotes[start:end]

        _log(f"Batch {batch_idx + 1}/{total_batches}: footnotes {start + 1}–{end} (calling Claude API...)")

        prompt = _build_llm_prompt(batch, current_style, target_style, display_map)

        try:
            response_text = _call_llm(prompt)
            results = _parse_llm_response(response_text)
        except Exception as e:
            _log(f"  API error on batch {batch_idx + 1}: {e}")
            errors += len(batch)
            continue

        # Map results back by display number
        result_map = {}
        for r in results:
            result_map[str(r.get("display", ""))] = r

        for fn in batch:
            fn_id = fn["footnote_id"]
            disp = display_map["id_to_display"].get(fn_id, "?")
            r = result_map.get(str(disp))

            if not r:
                errors += 1
                continue

            if r.get("skipped"):
                skipped += 1
                continue

            new_text = r.get("new_text", "")
            if not new_text or new_text == fn["text"]:
                skipped += 1
                continue

            ok = replace_footnote_text(output_path, fn_id, new_text)
            if ok:
                changed += 1
                changelog.append({
                    "fn_id": fn_id,
                    "display": disp,
                    "old": fn["text"][:100],
                    "new": new_text[:100],
                })
            else:
                errors += 1

    # Step 7: Save changelog
    plan_dir = output_path.parent / "placement"
    plan_dir.mkdir(parents=True, exist_ok=True)
    log_path = plan_dir / "restyle_changelog.json"
    log_path.write_text(json.dumps(changelog, indent=2, ensure_ascii=False), encoding="utf-8")

    _log(f"\nRestyle complete: {changed} converted, {skipped} skipped, {errors} errors")
    _log(f"Output: {output_path}")
    _log(f"Changelog: {log_path}")

    return {
        "output_path": str(output_path),
        "total": len(footnotes),
        "changed": changed,
        "skipped": skipped,
        "errors": errors,
        "changelog_path": str(log_path),
        "changelog": changelog,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Restyle .docx footnotes")
    parser.add_argument("--config", type=Path, required=True, help="Path to run_config.json")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    result = restyle_docx(cfg)
    print(json.dumps(result, indent=2, default=str))
