# latex-to-word

A Claude Code and Codex skill that converts academic manuscripts between LaTeX
and Microsoft Word in both directions, and assembles a single `.tex` from mixed
sources. It supersedes several earlier single-purpose converters, folding their
capabilities into one skill with three workflows.

## Overview

The skill offers three workflows. Pick the one that matches the task:

| Workflow | Direction | Use it when |
|---|---|---|
| **A — round-trip** | `.docx → .tex → .docx` | You edit in LaTeX but exchange drafts with Word-based co-authors, and the document is mostly prose and footnotes. Footnotes are preserved across the round-trip. |
| **B — one-way fidelity engine** | `.tex → .docx` | You need to deliver a finished LaTeX paper as high-fidelity Word for a Word-only journal or co-author, and the paper has regression/booktabs tables, equations, or cross-references that must survive. |
| **C — assemble from mixed sources** | (various) → `.tex` | You are building a pipeline that emits a single `.tex` from PDF, `.docx`, and LLM-generated content. This workflow is a set of knowledge patterns, not a script to run. |

**Which to choose.** Workflow B is the default for "deliver my LaTeX paper as
Word" — it builds native Word tables, OMML equations, real footnotes, and
embedded figures, and resolves cross-references, all of which plain pandoc drops
or mangles. Workflow A is faster but formatting-only (plain pandoc plus a
style-templated reference document); choose it when the exchange is prose and
footnotes and speed matters, and switch to B once the document depends on
tables, math, or cross-references. Workflow C applies only when you are authoring
a generator that produces LaTeX.

## Requirements

- **pandoc** — 3.x for the workflow B fidelity engine; ≥ 2.11 for the workflow A
  round-trip. (`winget install pandoc`, `choco install pandoc`, or your package
  manager.)
- **A LaTeX distribution** with `xelatex` and `latexmk` (TeX Live or MiKTeX).
  Required to produce the `.aux` that the workflow B engine reads, and to render
  TikZ/PGFPlots/algorithm environments to images. For TikZ/PGFPlots/algorithm
  rendering the install also needs `standalone.cls` / `preview.sty` and the
  document's own graphics packages.
- **Python 3** with:
  - `python-docx` and `lxml` — native Word table and OOXML construction (both
    workflows that build `.docx`).
  - `PyMuPDF` (imported as `fitz`) and `Pillow` — optional, for rasterizing pages
    during QA and for rendering LaTeX environments to images in workflow B.
- **Rendering for the QA check (optional):** Microsoft Word (COM automation, via
  the `pywin32` package) is preferred; LibreOffice (`soffice --headless
  --convert-to pdf`) is the fallback. Only needed when you want the output
  rendered to PDF and rasterized for a visual sanity check.
- **The document's body font** installed on the system, so Word or LibreOffice
  can render it faithfully.
- **Claude Code or Codex**, which discover and run the skill.

## Installation

Copy the `latex-to-word` folder into your host's user skills directory:

- Claude Code: `~/.claude/skills/latex-to-word/` (Windows:
  `%USERPROFILE%\.claude\skills\latex-to-word\`)
- Codex: `~/.agents/skills/latex-to-word/` (Windows:
  `%USERPROFILE%\.agents\skills\latex-to-word\`)

The folder should contain `SKILL.md`, `scripts/`, `references/`, and `gui.py` at
the top level. Restart the host or start a new session after installing it.
Invoke the skill with `/latex-to-word` in Claude Code or `$latex-to-word` in
Codex. Commands below that use `~/.claude/skills/` should use
`~/.agents/skills/` instead when the skill is installed for Codex.

## Workflow A — round-trip (`.docx → .tex → .docx`)

Convert a Word manuscript to LaTeX for editing (in Claude Code, Codex, or by
hand), then convert it back to Word, preserving footnotes throughout. The `tex → docx` step
is plain pandoc plus a style-templated `scripts/reference.docx`, so it is fast
and formatting-only; it does not build native tables or resolve cross-references.

Launch the GUI, which provides file browsers and one button per pipeline step,
with automatic XeLaTeX compilation and sanity checks:

```bash
python ~/.claude/skills/latex-to-word/gui.py
```

Or drive the two version-aware helpers directly, using the project layout
`input/ intermediate/ output/` (the file prefix always matches the folder name):

```bash
python scripts/docx_to_tex.py v1   # input/input_v1.docx -> intermediate/intermediate_v1.tex
# edit intermediate/intermediate_v2.tex ...
python scripts/tex_to_docx.py v2   # intermediate/intermediate_v2.tex -> output/output_v2.docx
```

Both helpers wrap the underlying pandoc calls and run a footnote-count sanity
check automatically. The `tex → docx` step reads output formatting (fonts, body
and footnote sizes, line spacing) from `scripts/reference.docx`; change the
formatting by editing that reference document rather than the pandoc command.
Regenerate a fresh reference document with `python scripts/gen_reference.py` if
needed. A companion script, `convert_bracket_footnotes.py`, converts inline
square-bracket citations (`[N: text]`) that some manuscripts use into proper
`\footnote{}` commands after conversion.

Full details, versioning conventions, and a troubleshooting table are in
[`references/roundtrip.md`](references/roundtrip.md).

## Workflow B — one-way high-fidelity (`.tex → .docx`)

Deliver a finished LaTeX paper as Word without losing the elements plain pandoc
cannot handle. Compile the source once so a current `.aux` exists (the engine
reads cross-reference and section numbers from it), then run:

```bash
python scripts/convert.py path/to/main.tex --out main.docx
# optional flags:
#   --aux main.aux --tables-dir tables --figures-dir figures
#   --font "Linux Libertine G" --workdir DIR --no-render
```

`--font` sets the Word body font; match the document's text font for best
fidelity and install the font so Word can see it. Without `--no-render`, the
output is rendered to PDF and the first pages are rasterized for a visual check.

The engine keeps pandoc for prose, footnotes, and equations, and routes the hard
elements through deterministic Python so the `.docx` converges with the compiled
PDF. It handles:

- **Native Word tables** built from estout/booktabs regression fragments and
  full `tabular`/`longtable` bodies — with booktabs rule weights (`\toprule`,
  `\midrule`, `\cmidrule`), `\multicolumn` horizontal spans, `\multirow`
  vertical merges, `threeparttable` notes, nested in-cell tabulars, and
  content-aware column widths scaled to fill the page.
- **User macros.** User `\newcommand`/`\renewcommand` definitions (including
  row-producing macros that expand to `\multirow … & … \\`) are expanded before
  table parsing, so tables that pandoc would collapse are built correctly.
- **TikZ / PGFPlots / algorithm rendering.** Graphics environments with no
  `\includegraphics` (TikZ pictures, PGFPlots axes, `algorithm2e` floats,
  subfigure panels) are compiled to standalone PDFs, rasterized, cached, and
  embedded as images.
- **Cross-reference resolution from the `.aux`.** `\cref`, `\Cref`, and `\eqref`
  are resolved to their rendered text (`Table 3`, `Section II`) using the
  compiled `.aux`.
- **OMML equations.** Math is emitted as native Word equations via pandoc, and
  footnote-reference runs are forced to superscript.
- Additional handling for `sidewaystable`/`sidewaysfigure` (landscape Word
  sections), `siunitx` units and numbers, `mhchem` chemistry, `glossaries` and
  acronyms, marginalia (`\marginpar`, `\todo`), and `\cite`/`\citep`/`\citet`
  resolution even without an external `.bib` (from `\bibcite` in the `.aux` or a
  manual `thebibliography`).

Full pipeline description and the hard-won fidelity techniques are in
[`references/tex-to-docx-engine.md`](references/tex-to-docx-engine.md).

## Workflow C — assemble `.tex` from mixed sources

A set of knowledge patterns (no script) for building a pipeline that combines
text from multiple sources into one `.tex`. The core idea is a two-track
architecture: LLM-generated content that is already valid LaTeX passes through
untouched, while text extracted from PDFs or `.docx` runs through a full
escaping pipeline. The reference also covers prompting an LLM to emit LaTeX
directly, stripping stray markdown code fences, `\DeclareUnicodeCharacter`
mappings for symbols common in extracted text, and Windows `pdflatex`
job-name handling for awkward filenames.

Read [`references/mixed-sources.md`](references/mixed-sources.md) and apply the
patterns in your own generator.

## Testing

`tests/` holds a 46-fixture regression corpus (`t01`–`t46`) covering booktabs,
longtable, tabularx/multirow, threeparttable, siunitx, math, lists, subfigures,
natbib and biblatex citations, two-column and multicol layouts, TikZ/PGFPlots,
algorithm2e, glossaries, nested tabulars, colortbl, multi-file `\input` chains,
rotating floats, and more. It ships **source `.tex` fixtures only** — compiled
PDFs, rendered PNGs, and `.docx` artifacts regenerate on each run.

```bash
python tests/run_tests.py    # compile each fixture, convert it, render both to PDF, rasterize
python tests/qa_metrics.py   # deterministic compiled-vs-converted text-diff metric
```

When a fixture reveals a defect, fix the converter under `scripts/`, never the
fixtures — the corpus is the ground truth.

## Limitations

- **Fidelity is element-level, not page-locked.** Word reflows text, so page
  breaks differ from the compiled PDF. Figure images are bound to their captions
  (keep-with-next) so a figure never splits from its caption, but long native
  tables may still break across pages (usually desirable).
- **Rendered graphics are images, not editable objects.** TikZ/PGFPlots/algorithm
  floats are embedded as images: faithful to the compiled look, but not natively
  editable in Word, and their text is image pixels rather than selectable text.
- **Workflow A is formatting-only.** Its `tex → docx` step does not build native
  tables or resolve cross-references; use workflow B when the document depends on
  those.
- **Very exotic packages or non-booktabs table styles** may still need
  per-document handling.
- Author placeholders and `\input` of external content that is neither a table
  nor a figure pass through as-is.

## Caution: `gui.py` launches Claude Code without permission prompts

The workflow A GUI (`gui.py`) specifically invokes the Claude Code CLI with
`--dangerously-skip-permissions` for its auto-edit and automatic XeLaTeX-error
repair loops. On that path, any tool call Claude makes runs without the usual
confirmation. Review `gui.py` and understand what the auto loops can do before
enabling that feature. This optional GUI automation is Claude Code-specific;
the skill's direct conversion workflows and command-line scripts work from
either host. The command-line scripts (`scripts/convert.py`,
`scripts/docx_to_tex.py`, `scripts/tex_to_docx.py`) do not bypass permissions.
