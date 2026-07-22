"""Standalone utility: restyle .tex footnotes from one citation style to another.

Uses the Anthropic Claude API for citation reformatting. This is an
alternative to the main pipeline (which is orchestrated by Claude Code
reading run_config.json and following phase-details.md).

Use this script when running outside Claude Code:
    python scripts/tex_restyle.py --config placement/run_config.json
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _DIR.parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from docx_restyle import _load_style_md, _call_llm, _parse_llm_response, BATCH_SIZE

# ── LaTeX footnote extraction ────────────────────────────────────────────


def _extract_footnotes(tex: str) -> list[dict]:
    """Extract all \\footnote{...} from tex, handling nested braces."""
    footnotes = []
    pattern = re.compile(r"\\footnote\{")
    pos = 0
    fn_num = 0

    while True:
        m = pattern.search(tex, pos)
        if not m:
            break

        start = m.start()
        brace_start = m.end() - 1  # position of opening {
        depth = 1
        i = m.end()

        while i < len(tex) and depth > 0:
            if tex[i] == "{":
                depth += 1
            elif tex[i] == "}":
                depth -= 1
            i += 1

        if depth != 0:
            pos = m.end()
            continue

        content = tex[brace_start + 1 : i - 1]
        fn_num += 1

        # Strip %CITE-PLACED marker
        content_clean = re.sub(r"%CITE-PLACED\s*\n?", "", content).strip()

        footnotes.append({
            "number": fn_num,
            "start": start,
            "end": i,
            "content": content,
            "content_clean": content_clean,
        })

        pos = i

    return footnotes


def _replace_footnote_content(tex: str, footnotes: list[dict],
                              replacements: dict[int, str]) -> str:
    """Replace footnote contents in reverse order to preserve positions."""
    sorted_fns = sorted(
        [(fn["number"], fn) for fn in footnotes if fn["number"] in replacements],
        key=lambda x: x[1]["start"],
        reverse=True,
    )
    for fn_num, fn in sorted_fns:
        new_content = replacements[fn_num]
        # Preserve %CITE-PLACED marker if original had it
        if "%CITE-PLACED" in fn["content"]:
            new_content = "%CITE-PLACED\n" + new_content
        tex = tex[:fn["start"]] + f"\\footnote{{{new_content}}}" + tex[fn["end"]:]
    return tex


# ── LLM prompt for .tex ──────────────────────────────────────────────────


def _build_tex_llm_prompt(footnotes_batch: list[dict], current_style: str,
                          target_style: str) -> str:
    """Build the LLM prompt for a batch of .tex footnotes."""
    current_md = _load_style_md(current_style)
    target_md = _load_style_md(target_style)

    fn_list = ""
    for fn in footnotes_batch:
        fn_list += f"\n[FN {fn['number']}] {fn['content_clean']}\n"

    return f"""You are restyling LaTeX footnote citations from {current_style.upper()} to {target_style.upper()}.

## Current citation style rules (for parsing input)
{current_md}

## Target citation style rules (for writing output)
{target_md}

## Footnotes to restyle
{fn_list}

## Instructions
For each footnote above, output a JSON array where each element has:
- "number": the footnote number (int)
- "new_text": the restyled footnote content in {target_style.upper()} format, using LaTeX commands (\\textit{{}}, \\textsc{{}}, etc.)
- "skipped": true if the footnote should not be restyled (discursive notes, contact info, case citations, legislation)

Rules:
1. Parse each citation and reformat it according to the target style rules above.
2. Convert cross-references (supra note N, Id., ibid) to the target style's convention.
3. Handle signals: remove them if the target style doesn't use signals.
4. Preserve LaTeX formatting commands appropriate for the target style.
5. Preserve discursive/non-citation content within footnotes unchanged.
6. For multi-citation footnotes (semicolon-separated), restyle each citation individually.
7. Preserve %CITE-PLACED markers if present — include them at the start of new_text.

Output ONLY the JSON array, no other text."""


# ── Public API ────────────────────────────────────────────────────────────


def restyle_tex(config: dict, progress_callback=None) -> dict:
    """Run the full .tex restyle pipeline using Claude API.

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

    # Step 1: Copy
    shutil.copy2(input_path, output_path)
    _log(f"Copied to {output_path}")

    # Step 2: Check API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        _log("ERROR: ANTHROPIC_API_KEY not set. Cannot run LLM restyle.")
        return {"output_path": str(output_path), "total": 0, "changed": 0,
                "skipped": 0, "errors": 1,
                "error_message": "ANTHROPIC_API_KEY environment variable not set",
                "changelog": []}

    # Step 3: Read and extract
    tex = output_path.read_text(encoding="utf-8")
    footnotes = _extract_footnotes(tex)
    _log(f"Extracted {len(footnotes)} footnotes")

    # Step 4: Send to Claude in batches
    changelog = []
    errors = 0
    changed = 0
    skipped = 0
    replacements = {}
    total_batches = (len(footnotes) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(footnotes))
        batch = footnotes[start:end]

        _log(f"Batch {batch_idx + 1}/{total_batches}: footnotes {start + 1}–{end} (calling Claude API...)")

        prompt = _build_tex_llm_prompt(batch, current_style, target_style)

        try:
            response_text = _call_llm(prompt)
            results = _parse_llm_response(response_text)
        except Exception as e:
            _log(f"  API error on batch {batch_idx + 1}: {e}")
            errors += len(batch)
            continue

        result_map = {r.get("number"): r for r in results}

        for fn in batch:
            fn_num = fn["number"]
            r = result_map.get(fn_num)

            if not r:
                errors += 1
                continue

            if r.get("skipped"):
                skipped += 1
                continue

            new_text = r.get("new_text", "")
            if not new_text or new_text == fn["content_clean"]:
                skipped += 1
                continue

            replacements[fn_num] = new_text
            changed += 1
            changelog.append({
                "fn_num": fn_num,
                "old": fn["content_clean"][:100],
                "new": new_text[:100],
            })

    # Step 5: Write replacements
    if replacements:
        tex = _replace_footnote_content(tex, footnotes, replacements)
        output_path.write_text(tex, encoding="utf-8")

    # Step 6: Save changelog
    plan_dir = output_path.parent / "placement"
    plan_dir.mkdir(parents=True, exist_ok=True)
    log_path = plan_dir / "restyle_changelog.json"
    log_path.write_text(json.dumps(changelog, indent=2, ensure_ascii=False), encoding="utf-8")

    _log(f"\nRestyle complete: {changed} converted, {skipped} skipped, {errors} errors")
    _log(f"Output: {output_path}")

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
    parser = argparse.ArgumentParser(description="Restyle .tex footnotes")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    result = restyle_tex(cfg)
    print(json.dumps(result, indent=2, default=str))
