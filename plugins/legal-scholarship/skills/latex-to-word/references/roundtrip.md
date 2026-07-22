# Workflow A — Round-Trip docx → tex → docx (Manuscript Editing)

This is **workflow A** of the `latex-to-word` skill. All paths are relative to the `latex-to-word` skill root: `scripts/reference.docx`, `gui.py`, and the helper scripts (`scripts/docx_to_tex.py`, `scripts/tex_to_docx.py`) remain valid because the original file layout was preserved during consolidation.

# Manuscript Editing Pipeline

Convert academic manuscripts between .docx and LaTeX for AI-assisted editing,
preserving footnotes throughout the round-trip.

## Project Folder Structure

```
project-root/
  input/              # Source .docx manuscripts
  intermediate/       # LaTeX working drafts + media/
  output/             # Final .docx files
  scripts/            # reference.docx + helper scripts
  prompts/            # Editing prompts for Claude
  manuscript-pipeline/  # This skill (SKILL.md)
```

Create any missing directories before running a step, and copy the skill's
reference doc into the project (Step 3 needs it; without it footnotes render at
full body size):

```bash
mkdir -p input intermediate output scripts prompts
cp ~/.claude/skills/latex-to-word/scripts/reference.docx scripts/
```

To run the helper scripts project-locally (`python scripts/docx_to_tex.py`,
`python scripts/tex_to_docx.py`), copy the skill's whole `scripts/` folder, not
just `reference.docx` — the helpers expect their siblings (e.g. `gen_reference.py`,
`toolcheck.py`) beside them.

## How to Run

Launch the GUI:

```bash
python ~/.claude/skills/latex-to-word/gui.py
```

The GUI provides file browsers for project root, input .docx, intermediate .tex,
and output folder. Action buttons run each pipeline step with built-in sanity
checks. An "Edits" text box sends free-form instructions to Claude Code CLI for
AI-assisted editing of the intermediate .tex. XeLaTeX compilation runs
automatically after conversion and editing steps; if errors occur, Claude Code
is invoked to fix them.

## Pipeline Overview

```
Step 1: docx -> tex      pandoc converts .docx to LaTeX
Step 2: editing           User edits .tex (in Claude Code or manually)
Step 3: tex -> docx       pandoc converts LaTeX back to .docx
```

---

## Step 1: Convert .docx to LaTeX

```bash
pandoc input/input_v1.docx \
  -t latex \
  --standalone \
  --pdf-engine=xelatex \
  --wrap=auto \
  --columns=80 \
  --extract-media=intermediate/media \
  -o intermediate/intermediate_v1.tex
```

**Naming convention**: The file prefix always matches the folder name.
`input/input_v1.docx` → `intermediate/intermediate_v1.tex` → `output/output_v1.docx`.

### Key flags

| Flag | Purpose |
|---|---|
| `-t latex` | LaTeX output with `\footnote{}` syntax |
| `--standalone` | Produce a compilable document with preamble and `\begin{document}` |
| `--pdf-engine=xelatex` | XeLaTeX-compatible output; preamble uses `fontspec` for Unicode |
| `--wrap=auto --columns=80` | Soft-wrap at 80 chars for readability |
| `--extract-media=intermediate/media` | Save embedded images alongside the .tex |

### What to expect

- Footnotes become inline `\footnote{...}` commands — the text is embedded
  directly at the point of reference, which makes them easy to read and edit.
- Images are extracted to `intermediate/media/` and referenced via
  `\includegraphics`.
- Some Word formatting (colored text, complex tables) may not survive; review
  the .tex after conversion.

### Post-conversion sanity check (REQUIRED)

After converting, **always** run the sanity check. Do not skip this step.

```bash
# Line count
wc -l intermediate/intermediate_v1.tex

# Footnote count
grep -coP '\\footnote\{' intermediate/intermediate_v1.tex

# First 3 footnotes (truncated preview)
grep -oP '\\footnote\{[^}]{0,80}' intermediate/intermediate_v1.tex | head -3
```

Print a summary like:

```
=== Conversion Summary ===
Lines:      1,247
Footnotes:  42
First 3 footnotes:
  \footnote{See Smith (2020) at 15.}
  \footnote{Compare Jones v. State, 123 F.3d 456 (2d Cir. 2019).}
  \footnote{The term ``regulatory capture'' was coined by ...}
```

If the footnote count is 0 but the original .docx had footnotes, the conversion
failed — investigate before proceeding.

---

## Step 2: Editing the LaTeX

The user edits `intermediate/intermediate_v1.tex` in Claude Code or a text
editor.

### Footnote syntax reference

- **Inline**: `\footnote{Footnote text here.}` placed at the point of
  reference in the text. There are no separate definitions — the footnote
  content lives right where it is referenced.

```latex
This claim is supported by evidence.\footnote{See Smith (2020) at 15.
This footnote can span multiple lines without any special indentation
rules.} Another point.\footnote{Compare Jones v. State, 123 F.3d 456
(2d Cir. 2019).}
```

### Special characters in footnotes

LaTeX reserves certain characters. When editing footnotes, escape these:

| Character | LaTeX escape |
|---|---|
| `%` | `\%` |
| `&` | `\&` |
| `$` | `\$` |
| `#` | `\#` |
| `_` | `\_` |
| `{` `}` | `\{` `\}` (only when literal, not as command delimiters) |

### Citation brackets vs. footnotes

**Not every `{...}` or `[...]` is a footnote.** When parsing or editing, do NOT
treat the following as footnote content:

- `[hereinafter ``SASAC'']` — short-form citation labels
- `[emphasis added]` — editorial signals
- `[internal quotation marks omitted]` — editorial signals
- `[sic]` — editorial notation
- `\footnote{...}` — these ARE footnotes

**Rule of thumb**: Only `\footnote{...}` commands contain footnote text. Square
brackets and other brace groups are editorial or part of LaTeX commands and
should be left alone.

---

## Step 3: Convert LaTeX back to .docx

```bash
pandoc intermediate/intermediate_v1.tex \
  -f latex \
  -o output/output_v1.docx \
  --reference-doc=scripts/reference.docx
```

### The reference document

`scripts/reference.docx` is the **single source of truth** for all output
formatting. Current settings:

- **Font**: Aptos
- **Body text**: 12pt
- **Footnote text**: 10pt
- **Text color**: Black
- **Line spacing**: Single

**To change output formatting, modify the reference doc — not the pandoc
command.** Open `scripts/reference.docx` in Word, update the styles (Normal,
Heading 1, Heading 2, Footnote Text, etc.), and save. Pandoc reads styles from
this file and applies them to the output.

To create or reset the reference doc, regenerate it with the skill's generator
(it bakes in all the settings above, including 10pt Footnote Text) and copy the
result into the project:

```bash
python ~/.claude/skills/latex-to-word/scripts/gen_reference.py
cp ~/.claude/skills/latex-to-word/scripts/reference.docx scripts/
```

Do NOT use `pandoc --print-default-data-file reference.docx` as the reference:
pandoc's default styles leave Footnote Text with no explicit size, so footnotes
inherit the body size and render at 12pt instead of 10pt.

### Post-conversion sanity check (REQUIRED)

After converting back to .docx, verify the round-trip preserved content:

```bash
# Quick check: convert the output back to tex temporarily and compare
pandoc output/output_v1.docx -t latex -o /tmp/roundtrip_check.tex

# Compare footnote counts
echo "Original .tex footnotes:"
grep -coP '\\footnote\{' intermediate/intermediate_v1.tex
echo "Round-trip .tex footnotes:"
grep -coP '\\footnote\{' /tmp/roundtrip_check.tex

# Compare line counts
echo "Original .tex lines:"
wc -l < intermediate/intermediate_v1.tex
echo "Round-trip .tex lines:"
wc -l < /tmp/roundtrip_check.tex
```

If footnote counts diverge, inspect the diff before delivering the output.

---

## Versioning

Use version suffixes to track iterations through the pipeline. The file prefix
always matches the folder name:

```
input/input_v1.docx              # Original from co-author
intermediate/intermediate_v1.tex # First conversion
intermediate/intermediate_v2.tex # After Claude editing pass
output/output_v2.docx            # Converted back after edits
input/input_v3.docx              # Revised version from co-author
intermediate/intermediate_v3.tex # New conversion
...
```

### Conventions

- **File prefix = folder name**: `input/input_v1.docx`,
  `intermediate/intermediate_v1.tex`, `output/output_v1.docx`. This makes it
  unambiguous which stage a file belongs to even when viewed outside its folder.
- **v1** = initial version received or created.
- Increment the version when the content changes meaningfully (an editing pass,
  a co-author revision, structural reorganization).
- The version in `intermediate/` and `output/` should match:
  `intermediate/intermediate_v2.tex` produces `output/output_v2.docx`.
- Keep prior versions in their folders (don't delete `intermediate_v1.tex` when
  creating `intermediate_v2.tex`) so you can diff between versions.
- For minor fixes that don't warrant a new version, you can use suffixes like
  `intermediate_v2_fix.tex`, but prefer incrementing when in doubt.

---

## Quick Reference

### Full pipeline (one manuscript, version 1)

```bash
# Setup
mkdir -p input intermediate output scripts prompts
cp ~/.claude/skills/latex-to-word/scripts/reference.docx scripts/

# Step 1: docx -> tex
pandoc input/input_v1.docx \
  -t latex --standalone --pdf-engine=xelatex \
  --wrap=auto --columns=80 \
  --extract-media=intermediate/media \
  -o intermediate/intermediate_v1.tex

# Sanity check
wc -l intermediate/intermediate_v1.tex
grep -coP '\\footnote\{' intermediate/intermediate_v1.tex
grep -oP '\\footnote\{[^}]{0,80}' intermediate/intermediate_v1.tex | head -3

# Step 2: edit intermediate/intermediate_v1.tex (save as intermediate_v2.tex after editing)

# Step 3: tex -> docx
pandoc intermediate/intermediate_v2.tex \
  -f latex \
  -o output/output_v2.docx \
  --reference-doc=scripts/reference.docx

# Final sanity check
pandoc output/output_v2.docx -t latex -o /tmp/roundtrip_check.tex
grep -coP '\\footnote\{' intermediate/intermediate_v2.tex
grep -coP '\\footnote\{' /tmp/roundtrip_check.tex
```

The two version-aware helper scripts wrap these pandoc calls and run the sanity
checks automatically (`python scripts/docx_to_tex.py v1`, then
`python scripts/tex_to_docx.py v2`).

### Common issues

| Problem | Cause | Fix |
|---|---|---|
| 0 footnotes in .tex | Word used endnotes not footnotes, or non-standard footnote style | Convert endnotes to footnotes in Word first |
| Garbled tables | Complex merged cells in Word | Simplify table in Word before conversion, or edit table manually in .tex |
| Missing images | `--extract-media` path wrong | Check `intermediate/media/` exists and paths in .tex are correct |
| Formatting wrong in output .docx | reference.docx styles don't match expectations | Edit styles in `scripts/reference.docx`, not pandoc flags |
| Footnotes same size as body text | Output built without `scripts/reference.docx`, or with pandoc's default reference (its Footnote Text style has no size) | Copy the skill's `reference.docx` into `scripts/` (or run `gen_reference.py`) and reconvert |
| Footnote count mismatch after round-trip | Malformed `\footnote{}` syntax in .tex | Check for unmatched braces in footnotes |
| Special chars cause LaTeX errors | Unescaped `%`, `&`, `$`, `#`, `_` | Escape with backslash: `\%`, `\&`, etc. |

## Dependencies

- **pandoc** (>= 2.11 recommended): `winget install pandoc` or
  `choco install pandoc`
- **Microsoft Word** (for editing `scripts/reference.docx` styles)

## Notes

- Always run the sanity check after each conversion step. Skipping it risks
  delivering a manuscript with missing footnotes or corrupted structure.
- The pipeline is format-agnostic for the editing step — any text editor works,
  but Claude Code is ideal for substantive editing passes.
- If a co-author sends a new .docx revision, start a new version number rather
  than overwriting the existing intermediate .tex.
