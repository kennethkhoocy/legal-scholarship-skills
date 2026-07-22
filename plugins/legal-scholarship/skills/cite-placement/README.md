# cite-placement

A Claude Code skill that places pre-screened literature citations into a LaTeX
or Word manuscript, or restyles the citations already in one. A single Tkinter
launcher selects the mode and its options.

## Citation integrity — no fabricated references

This skill never invents citations. It works only with references the author has
already gathered and screened:

- **Placement draws exclusively from a user-supplied, pre-screened bibliography.**
  The inline and footnote modes place citations only from the `.xlsx` spreadsheet
  of screened references you provide. The skill decides *where* an existing
  reference belongs; it has no path that conjures a new citation from the model's
  own memory.
- **Every reference can be verified against authoritative databases.** The
  optional verification pass (Phase 1.5) checks each reference against OpenAlex
  and CrossRef — with Google Scholar as an additional cross-check when a
  `SEARCHAPI_API_KEY` is set — and flags dangling citation keys and entries it
  cannot confirm.
- **Restyling reformats; it does not re-source.** When converting citations from
  one style to another, the skill rewrites formatting only and leaves case
  citations, legislation, and discursive footnotes untouched, so no substantive
  citation content is altered or introduced.

Together these properties address the fabricated-citation risk that attends
LLM-assisted writing: the bibliography is the author's, and the skill's role is
placement and formatting rather than invention.

## Overview

The skill has three modes, selected by a run button in the launcher:

1. **Inline placement** — places screened citations as inline `\cite{}`,
   `\citet{}`, or `\citep{}` commands with a compiled `references.bib`
   bibliography. For economics, finance, and social-science journals using
   BibTeX/biber (APA, MLA, Harvard, Chicago author-date, IEEE, Vancouver).
   `.tex` only.
2. **Footnote placement** — places screened citations as full formatted
   `\footnote{}` (LaTeX) or native Word footnotes (OOXML), with one-click legal
   and notes style selection (Bluebook, OSCOLA, Chicago notes-bib, APA 7th,
   McGill) and Id./supra short-form post-processing. `.tex` or `.docx`.
3. **Restyle** — converts ALL existing footnote citations from one style to
   another, without a spreadsheet. `.tex` or `.docx`.

Given a `.tex`/`.docx` manuscript and (for placement) an `.xlsx` spreadsheet of
screened citations, a placement run maps the manuscript at the paragraph level,
ingests the spreadsheet into BibTeX, plans where each citation belongs using
parallel sub-agents, inserts the citations into a new copy of the manuscript,
and compiles.

## Requirements

- Python 3.10+
- `openpyxl` (`pip install openpyxl`) for spreadsheet ingestion.
- For `.docx` manuscripts (footnote and restyle modes): `python-docx`, `lxml`,
  and `pydantic` — `pip install python-docx lxml pydantic` (see
  `requirements-docx.txt`). `.tex`-only usage needs no extra dependencies.
- A LaTeX distribution: `pdflatex` + `bibtex`/`biber` for inline mode; `xelatex`
  for footnote and restyle modes.
- Claude Code, invoked via `/cite-placement`.
- `SEARCHAPI_API_KEY` in the environment to enable optional Google Scholar
  verification (Phase 1.5). Without it, verification falls back to OpenAlex and
  CrossRef only.

## Directory Structure

```
cite-placement/
├── README.md                        # This file
├── SKILL.md                         # Router: modes, launcher protocol, commands
├── requirements-docx.txt            # Extra deps for .docx support
├── scripts/
│   ├── launcher.py                  # Unified Tkinter GUI (3 run buttons + utilities)
│   ├── short_form.py                # Phase 6: style-aware short-form substitution
│   ├── merge_adjacent_footnotes.py  # Phase 5 post-proc: merge adjacent \footnote{}
│   ├── reorder_crossrefs.py         # Fix supra/Id. after manual edits
│   ├── strip_citations.py           # Remove all %CITE-PLACED footnotes
│   ├── migrate_markers.py           # Add %CITE-PLACED to legacy footnotes
│   ├── docx_restyle.py              # Standalone .docx restyle driver
│   ├── tex_restyle.py               # Standalone .tex restyle driver
│   └── core/
│       ├── ingest_citations.py      # .xlsx → citations.json + references_new.bib
│       ├── verify_citations.py      # Phase 1.5 verification (--mode inline|footnotes)
│       └── docx_support/            # OOXML footnote read/write (from word-docx skill)
├── references/
│   ├── phase-details-inline.md      # Inline-mode workflow (5 phases)
│   ├── phase-details-footnotes.md   # Footnote-mode workflow (6 phases) + Restyle Pipeline
│   └── styles/                      # 5 style packs (.md + .json): bluebook, oscola,
│                                    #   chicago, apa, mcgill
└── tools/
    └── cite-restyle/                # Standalone restyle app source (.exe via GitHub Release)
```

## Quick Start (for colleagues)

This quick start walks through a restyle run — the most common colleague task.
Placement runs follow the same launch flow with a different run button.

### 1 — Install Claude Code

```
npm install -g @anthropic-ai/claude-code
```

Run `claude` in your terminal to verify it works. You will need an Anthropic
account or an organisation seat.

### 2 — Install the skill

Copy the `cite-placement` folder to your Claude Code skills directory:

- Windows: `%USERPROFILE%\.claude\skills\cite-placement\`
- macOS: `~/.claude/skills/cite-placement/`
- Linux: `~/.claude/skills/cite-placement/`

The folder should contain `SKILL.md`, `scripts/`, and `references/` at the top
level. No further configuration is needed — Claude Code discovers skills
automatically.

### 3 — Launch the GUI

Open a terminal, run `claude`, and type:

```
/cite-placement
```

Claude Code launches a Tkinter GUI window. If it doesn't appear, make sure
Python's tkinter is installed (it ships with most Python distributions).

### 4 — Configure the restyle

In the GUI:

- **Input Manuscript** — Browse and select your `.docx` or `.tex` file.
- **Output File** — Auto-fills as `<name>_cited.<ext>`; change it if you prefer a
  different name or location.
- **Restyle section** — Set **Current Style** to the style your manuscript uses
  (e.g., Bluebook) and **Restyle To** to the target style (e.g., OSCOLA).
- Click **Restyle**.

The `.xlsx` field is for placement only; leave it empty when restyling.

### 5 — Claude Code runs the pipeline

After the GUI closes, Claude Code automatically:

1. Copies your manuscript to the output path (never modifies the original).
2. Extracts all footnotes.
3. Reformats each footnote from the current style to the target style — Claude
   Code itself does the reformatting.
4. Writes the restyled footnotes back into the output file.
5. Reports how many footnotes were converted, skipped, and any errors.

This typically takes 1–3 minutes for a 200-footnote manuscript. A changelog is
saved at `<output_dir>/placement/restyle_changelog.json`.

### 6 — Review the output

Open the output file in Word or your LaTeX editor and check that:

- The citation format matches the target style.
- Cross-references (e.g., `(n 3)` for OSCOLA) point to the correct footnotes.
- Discursive footnotes (author commentary, data notes), case citations, and
  legislation were preserved unchanged.

## What the Restyle Converts

```
✓ Journal article citations (author, title, volume, journal, page, year)
✓ Book and working-paper citations
✓ Cross-references (Id./ibid, supra note N / (n N))
✓ Introductory signals (See, See also, Cf. — added or removed per style)
✓ Internal references (Infra/Supra Part → "see Part X below/above")
✓ Author formatting (& vs "and", et al. vs "and others")
✓ Trailing punctuation (period vs no period)
✓ Asterisk/symbol footnote numbering (automatically detected)

✗ Case citations — preserved as-is (jurisdiction-specific)
✗ Legislation — preserved as-is
✗ Discursive footnotes — preserved as-is
```

## Placement Pipeline

To place NEW citations from an `.xlsx` spreadsheet, fill in the `.xlsx` field,
select a citation style, and click **Inline Placement** or **Footnote
Placement**. The pipeline then runs automatically through all phases:

| Phase | Inline mode | Footnote mode |
|---|---|---|
| 1 | Manuscript mapping + package detection | Manuscript mapping + footnote classification |
| 1.5 | (Optional) verify `\cite{}` keys vs `.bib` + APIs | (Optional) verify footnote citations vs APIs |
| 2 | Ingest `.xlsx` → JSON + BibTeX | Ingest `.xlsx` → JSON + BibTeX |
| 3 | Assign → per-section sub-agents → consolidate | Assign → per-section sub-agents → consolidate |
| 4 | Human-in-the-loop review (if enabled) | Human-in-the-loop review (if enabled) |
| 5 | Insert cites, merge `.bib`, compile (pdflatex + bibtex/biber) | Insert footnotes, compile (xelatex) |
| 6 | — | Short-form post-processing (Id./supra) |

See `SKILL.md` for the launcher protocol, the full command reference, and the
`run_config.json` shapes; see `references/phase-details-inline.md` and
`references/phase-details-footnotes.md` for per-phase detail.

## Standalone Scripts

Deterministic ingestion (no LLM) of an `.xlsx` spreadsheet into BibTeX:

```bash
python scripts/core/ingest_citations.py \
    --input citations.xlsx \
    --output-json citations.json \
    --output-bib references_new.bib \
    --existing-bib references.bib
```

Optional: `--min-score N` skips spreadsheet rows whose `screening_score` is below N (default 0 = no filtering).

Verify existing citations against OpenAlex, CrossRef, and optionally Google
Scholar (mode selects the input shape and report schema):

```bash
# inline: verify \cite{} keys against the .bib
python scripts/core/verify_citations.py --mode inline \
    --citations placement/existing_citations.json \
    --bib references.bib \
    --output placement/audit_report.json \
    --spreadsheet citations.xlsx

# footnotes: verify extracted footnote citations
python scripts/core/verify_citations.py --mode footnotes \
    --footnotes placement/existing_footnotes.json \
    --output placement/audit_report.json \
    --spreadsheet citations.xlsx
```

Set `SEARCHAPI_API_KEY` in your environment to enable Google Scholar
verification.

## Standalone .exe (tools/cite-restyle)

For colleagues without a Python or Claude Code setup, the restyle workflow is
also packaged as a standalone Windows executable built from the source in
`tools/cite-restyle/` using its bundled PyInstaller `.spec`. The `.exe` is
distributed **only** as a GitHub Release asset and is never committed to the
repository (the built binary is large and platform-specific). A short
`README-dist.txt` ships alongside the `.exe` in the release, explaining how to
run it and which styles it supports. To rebuild, run PyInstaller against the
`.spec` in `tools/cite-restyle/` and upload the resulting `.exe` plus
`README-dist.txt` to a new release.

## Troubleshooting

- **The GUI doesn't open.** Confirm tkinter is installed:
  `python -c "import tkinter"`. On Ubuntu/Debian: `sudo apt install python3-tk`.
- **"Permission denied" on the output file.** The output file may be open in
  Word, or it lives in a Dropbox- or OneDrive-synced folder that has locked it.
  Close Word and/or write to a local directory.
- **Claude Code doesn't recognise `/cite-placement`.** Check the skill is in the
  correct directory with `SKILL.md` at the top level, then restart Claude Code.
- **Some footnotes weren't converted.** Discursive footnotes, case citations,
  and legislation are intentionally skipped — check the changelog for details.
- **Undefined citation warnings (inline mode).** Check `.bib` key spelling and
  that `\bibliography{}` / `\printbibliography` is present; a missing `.bst`
  file means the relevant LaTeX package needs installing.

## Key Design Decisions

- **Non-destructive**: never modifies the original manuscript — always creates a
  new copy.
- **Re-run safe**: `.bib` merging avoids duplicates; placement plans are
  incremental, keyed on the `planned_keys` header.
- **Agentic Phase 3**: parallel sub-agents (one per section) prevent citation
  drops on large batches.
- **Content-agnostic**: works for any academic discipline — no hardcoded section
  names.
- **Style-swappable**: footnote citation styles change via the GUI without
  re-running placement decisions; the restyle mode converts existing citations
  between styles.

## Lineage

This skill consolidates the former `cite-placement-inline` and `cite-placement-footnotes` skills into a single router with a shared launcher and a common `placement/` workspace.
