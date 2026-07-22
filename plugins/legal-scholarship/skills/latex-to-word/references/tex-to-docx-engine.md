# Workflow B — One-Way High-Fidelity tex → docx (Fidelity Engine)

This is **workflow B** of the `latex-to-word` skill. All paths are relative to the `latex-to-word` skill root (`scripts/convert.py`, `tests/`); the file layout was preserved during consolidation, so every path below resolves under `~/.claude/skills/latex-to-word/`.

# LaTeX → Word with format fidelity

## Problem

`pandoc file.tex -o file.docx` is the right tool for **prose, footnotes, and
equations**, but on a real academic manuscript it fails on everything else:

- Custom table macros (`\estauto`, `\@@input`) and estout fragments are dropped or
  emitted as raw text — pandoc never sees a `tabular`.
- User `\newcommand` row macros (e.g. `\GroupRows{...}` expanding to several table
  rows) are never executed, so the table collapses to garbled single cells.
- `cleveref` references (`\cref`, `\Cref`, `\eqref`) are not resolved — they vanish
  or become `[?]`.
- `\author{...\thanks{...}}` title notes become Word footnotes 1 and 2, shifting
  every body footnote by +2.
- Wide tables overflow; multi-panel and longtable bodies collapse; `\multirow`
  vertical spans flatten; nested in-cell tabulars shatter the parent row.
- TikZ / PGFPlots diagrams, `algorithm2e` floats, and `glossaries`/`\printglossaries`
  output are silently dropped (pandoc cannot render them).

This skill keeps pandoc for what it is good at and routes the hard elements through
deterministic Python so the `.docx` converges with the compiled PDF.

## Approach (pipeline)

```
main.tex (+ main.aux, tables/, figures/)
   │
   ├─ PREPROCESS (deterministic, before pandoc):
   │     • expand user \newcommand/\renewcommand/\providecommand (incl optional args),
   │       so row macros like \GroupRows{...} become real \multirow/&/\\ table rows
   │     • render un-renderable graphics envs to images (render_latex_env.py):
   │       tikzpicture / pgfplots axis / algorithm2e → standalone-compiled PNG,
   │       then rewrite the float to \includegraphics{<png>} (figure pipeline handles it)
   │     • glossaries: parse \newglossaryentry/\newacronym from the ORIGINAL preamble,
   │       expand \gls first-use ("long (SHORT)" → "SHORT"), and replace
   │       \printglossaries with \section*{Glossary}/\section*{Acronyms} lists
   │
   ├─ body preparation (internal convert.py stage) ─► body.docx   (pandoc)
   │     derive main_pandoc.tex:
   │       • neutralize \author\thanks  (body footnotes start at 1)
   │       • resolve \cref/\Cref/\eqref from .aux  → "Table 3" / "Section II"
   │       • table floats  → placeholder paragraph  %%TABLE:label%%   (escaped \%\% so it survives pandoc)
   │       • figure floats → caption + %%FIGURE:path%%
   │       • strip custom macros (\estauto, \@@input, \sym, \href→text)
   │     build a font-matched reference.docx (Normal/Headings/Footnote Text)
   │     pandoc main_pandoc.tex --reference-doc=reference.docx -o body.docx   (native footnotes + OMML math)
   │
   ├─ tex_table_to_docx.py      (estout / booktabs FRAGMENTS → native Word table)
   ├─ full_tabular_to_docx.py   (multi-panel / \input / \@@input / inline \begin{tabular} /
   │                             longtable + \multirow vMerge / nested in-cell tabular → native Word table)
   │
   ├─ assembly (internal convert.py stage; assemble.py is only a thin
   │            compatibility shim that re-enters convert.py) ─► inject each native
   │            table at its %%TABLE%% anchor and each image at its %%FIGURE%%
   │            anchor (moves built elements into place)
   │
   └─ postprocess_docx.py ────────► force every footnote-reference run to superscript
                                    → main.docx
```

`convert.py` orchestrates all of it. Table routing is content-based (full-tabular
if the float/fragment has `\begin{tabular}`/`\begin{longtable}`, else estout — no
hardcoded labels); paths, font, and crefname are parameters.

## Usage

```bash
python scripts/convert.py path/to/main.tex \
    [--out main.docx] [--aux main.aux] \
    [--tables-dir tables] [--figures-dir figures] \
    [--font "Linux Libertine G"] [--workdir DIR] [--no-render]
```

- A current `.aux` is **required** (cleveref numbers and section numbers come from
  it). Compile the source once (`pdflatex`/`latexmk`) before converting.
- `--font` is the Word body font; match the document's text font for best fidelity
  (e.g. Linux Libertine, Times New Roman). Install the OTF/TTF so Word can see it.
- TikZ/PGFPlots/algorithm rendering needs a working TeX install (latexmk/pdflatex)
  with `standalone.cls` / `preview.sty` and the document's own graphics packages.
- Without `--no-render`, the doc is rendered to PDF (Word COM, LibreOffice fallback)
  and the first pages rasterized for a visual sanity check.

## Key fidelity techniques (hard-won — keep these)

1. **Set table borders on the row's real cell elements, not `cell(r,c)`.**
   python-docx `Table.cell(r,c)` mis-maps under horizontal merges (`\multicolumn`),
   so a `seen`-dedup silently skips columns and the bottom rule develops gaps.
   Iterate `tbl.rows[r]._tr.tc_lst` and set borders on each `<w:tc>` directly.
2. **Content-aware column widths, scaled to FILL the available width** (like a
   journal table): size each column to its widest cell, then scale the set so it
   sums to the available width — up for a narrow table (so it spans margin-to-margin
   instead of huddling at content width) and down for a wide one. Uniform widths
   wrap wide content (CI intervals, "Difference" headers) and waste space on narrow
   numeric columns; not filling leaves narrow tables looking small on the page.
3. **Booktabs mapping:** `\toprule`/`\bottomrule` → heavy top/bottom border (sz≈10),
   `\midrule` → light full-width rule, `\cmidrule(lr){a-b}` → light *partial* rule
   = top borders on cells a..b of the FOLLOWING row. **No vertical borders.**
4. **Protect `\makecell{a\\b}` before splitting rows on `\\`** — its internal `\\`
   otherwise shatters row parsing (garbled cells like `[1][AboveMedian_i...]`).
5. **Inline LaTeX cleaner** (`inline_to_runs`): handle `\$`→$ and `\%`→% BEFORE
   stripping `$`; `^{}`/`_{}` → super/subscript runs; `\sym{}` → superscript;
   `\textit/\textbf`; a math-symbol map (Δ β μ × ≤ → …); and `\cref{}` resolved via
   the aux number map. `\sym{*}` stars must be superscript.
6. **Placeholders must not be LaTeX comments.** `%%TABLE:..%%` written literally is
   a comment and vanishes through pandoc — emit it escaped (`\%\%...\%\%`) so it
   survives as literal `%%...%%` text, then match it in the assembler.
7. **Neutralize `\author\thanks`** so body footnotes start at 1 (pandoc otherwise
   makes the two title notes footnotes 1-2 and desyncs everything).
8. **Force footnote-reference runs to superscript** (`postprocess_docx.py`): pandoc
   occasionally leaves a marker at baseline; setting run-level `vertAlign` on every
   `w:footnoteReference` makes them uniform.
9. **`sidewaystable` → its OWN landscape page**, the faithful rendering of the
   rotated float. `insert_doc_landscape_before` wraps the built block (caption +
   table + notes) in a next-page **landscape Word section** — a portrait section
   boundary just before it, the page width/height swapped + `w:orient="landscape"`
   for the block, and the portrait body resuming on a new page after — by deep-
   copying the body's final `sectPr` (so headers/footers/margins carry through) and
   stamping `w:type=nextPage` on each boundary. The table itself is built at the
   wider landscape width (≈9in) and the full 11pt font. It is NOT enough to widen
   the available width alone: a 9in table dropped into a 6.5in portrait column
   overflows the margin (the prior bug — the `landscape` flag set a 9in width but
   never created a section, so it stayed inline in portrait).
10. **Compile un-renderable graphics environments to images** (`render_latex_env.py`).
    Any figure float with no `\includegraphics` (a `tikzpicture`/`pgfplots`/`axis`, a
    `subfig` `\subfloat` panel layout, raw `\framebox`/`\rule` drawings) and
    `algorithm2e` floats cannot be drawn natively. Build a `standalone`
    document reusing the original preamble (tikz libraries, pgfplotsset, algorithm2e
    SetKw…), compile to PDF, rasterize with PyMuPDF (~300 dpi), cache by content
    hash, and rewrite the environment to `\includegraphics{<png>}` BEFORE
    `replace_floats`. Subfigure tikz pictures each become their own image (subcaption
    mapping preserved). Must DEGRADE GRACEFULLY: a compile failure omits the image
    but never aborts the conversion (the old failure mode synthesized an `idx{n}`
    path → `FileNotFoundError` → rc 2). Caption prefix is env-aware ("Algorithm N:"
    vs "Figure N:").
11. **Expand user `\newcommand` before table parsing.** Row-producing macros
    (`\GroupRows{...}` → `\multirow … & … \\ … \midrule`) are opaque to the splitter
    until expanded; substitute `#1..#n` brace-balanced, re-scan for nesting. Strict
    no-op when the document defines no such macros; DENYLIST length redefinitions
    (`\arraystretch`, `\tabcolsep`, …) so `\renewcommand{\arraystretch}{1.16}` stays
    inert.
12. **`\multirow{n}{*}{label}` → real vertical Word merge** (`w:vMerge` restart/
    continue). Add a `rowspan` to the cell spec, reconstruct the omitted leading
    column in the continuation rows (they begin with `&`), and emit the merge at the
    XML level. Gate on `rowspan>1` so single-row tables are untouched.
13. **Environment-aware row/cell splitting for nested tabulars.** The row/cell
    splitter must count `\begin{tabular}`/`\end{tabular}` depth so a nested in-cell
    tabular's inner `\\` and `&` do not shatter the parent row, and the outer-tabular
    slice must match the DEPTH-COUNTED `\end{tabular}` (not the first one). Render the
    nested tabular as a multi-line cell (one `add_break()` per nested row). The
    threeparttable `\tnote{a}`/`tablenotes` path then attaches as for plain
    threeparttable.
14. **Glossaries are package state, so reconstruct it.** Parse
    `\newglossaryentry`/`\newacronym` from the ORIGINAL source (the preamble is
    stripped before body passes), expand `\gls` with first-use awareness (acronym
    first use → "long (SHORT)", later → "SHORT"; glossary entry → name), and replace
    `\printglossaries` (and its `\let` aliases / `\printnoidxglossaries`) with
    generated `\section*{Glossary}` + `\section*{Acronyms}` description lists, sorted
    as the package prints them. Sibling to the `acronym`-package pass; disjoint
    macro families, no collision; strict no-op without glossaries.
15. **Bind figure blocks with keep-with-next.** Set `keep_with_next` on every
    paragraph of a figure block (image + subcaptions) and `keep_together` on all,
    so Word never splits a figure from its caption across a page break — LaTeX
    float behaviour, where the image and caption always travel together.
16. **Render siunitx units and numbers** (`siunitx_expand.py`). Expand `\si{...}`,
    `\SI{v}{u}`, `\num{n}`, and `\tablenum{n}` to Unicode — a unit/prefix map
    (`\meter`→m, `\kilo`→k, `\mole`→mol, …), `\per`→/, `\squared`→², e-notation
    `6.022e23`→6.022×10²³ with superscript exponents, and separate-uncertainty
    `1.23(4)`→1.23 ± 0.04 — in both prose and table cells, plus bare e-notation in
    `S` columns. Strict no-op without siunitx. (NB: siunitx itself must load — a
    siunitx/expl3 version skew silently breaks `S` columns; pin a compatible pair.)
17. **Render mhchem `\ce{}` chemistry** (`mhchem_unicode.py`). Convert `\ce{...}` to
    Unicode — subscript a digit after a letter or `)` (H₂O), keep a leading digit as a
    stoichiometric coefficient (2 H₂O), superscript charges (SO₄²⁻), arrows `->`→→ /
    `<=>`→⇌, and keep state labels `(aq)`/`(g)` — in prose and table cells; render a
    display reaction (`$$\ce{…}$$`) as a centred paragraph with its equation number
    rather than leaking raw `\ce`. No-op without mhchem.
18. **Resolve citations even without a `.bib`.** Detecting `\cite`/`\citep`/`\citet`
    must NOT require an external bibliography: a manual `\begin{thebibliography}` (or a
    pre-built `.bbl`) is a valid, common form. Parse `\bibcite{key}{{N}{year}{Author}…}`
    from the `.aux` and resolve `\citet`→"Author [N]", `\citep`→"[N]",
    `\citep[p. 5]`→"[N, p. 5]", multi-key→"[N, M]"; render the `thebibliography` list.
    Never hard-crash when citations lack a `.bib` — degrade to a best-effort or warning.
    For biblatex, EXPAND `\jobname` when resolving `\addbibresource{\jobname.bib}` (a
    `filecontents` `.bib` lands on disk as `<stem>.bib`), and route `\printbibliography`
    to the pandoc references container so the citeproc-generated list actually renders.
19. **Rotated floats and boxes.** Add `sidewaysfigure`/`sidewaysfigure*` (rotating) to
    the figure-float set so a rotated, image-less figure compiles-to-image and embeds
    rather than vanishing; map `sidewaystable` to a landscape section. Unwrap
    `\rotatebox[opts]{angle}{text}`→`text` in prose and cells so the angle (`90`) never
    leaks into a cell label.
20. **Preserve marginalia.** `\marginpar{…}`/`\marginnote{…}` and `\todo{…}` are dropped
    by pandoc; convert their content into a real Word footnote (or inline `[TODO: …]`
    note) so it survives instead of vanishing. No-op when those macros are absent.
21. **Table body sizing + tight single-spacing (publication house style).** Native
    tables are sized UP from the LaTeX `\small`/`\footnotesize` so the Word output
    reads comfortably, and every row is uniformly single-spaced. One shared policy,
    `full_tabular_to_docx.table_data_pt(total_cols, landscape)`, drives the cell font
    for BOTH engines (estout passes data-cols+1; full-tabular passes its parsed
    count): `landscape → 11pt`; portrait `≤7 cols → 11pt`, `8 → 10pt`, `≥9 → 9pt`
    (stepped down only so wide tables still fit the portrait column). Spacing is made
    tight everywhere — `space_before = space_after = 0` (the `\addlinespace` 4pt gap
    and the longtable 1.08 leading are dropped), `line_spacing = 1.0`. Combined with
    the fill-to-width scaling (#2), tables span margin-to-margin at a readable size
    instead of huddling small with loose inter-row gaps. **Captions match the table
    font size**: a table caption is rendered at that table's own `data_pt` (so a
    9pt wide table gets a 9pt caption, an 11pt table an 11pt caption), and figure
    captions use the table-body default (`FIGURE_CAPTION_PT = 11pt`) so tables and
    figures caption at the same size. Table NOTES stay smaller (8.2–8.5pt), the
    conventional table-note size.

## QA loop

Render the output `.docx` → PDF (Word COM = truest, LibreOffice fallback), rasterize
pages (`render_all_pages.py`), and compare to the compiled PDF — element-wise, since
Word and LaTeX paginate differently. A pixel rule-gap detector (`detect_rules.py`)
and a last-row border check (`inspect_lastrow.py`) help debug table rules.

## Validation — diagnostic test corpus

`tests/` holds a 46-paper diagnostic corpus (`t01`–`t46`) spanning booktabs,
longtable, tabularx/multirow, threeparttable, siunitx, math/theorems, lists,
subfigures, natbib & biblatex citations, two-column, wrapfig, multicol, listings,
hyperref, frontmatter, resizebox, complex merges, enumitem, acronyms, tcolorbox,
TikZ/PGFPlots, algorithm2e, glossaries, nested-tabular + table footnote, longtable
+ inline-math + multirow, a dense integration paper, subfig/`\ContinuedFloat`,
booktabs `\multicolumn` spanners + `\cmidrule`, siunitx `S`-columns/units, hyperlinks
+ colour, advanced display math (align/cases/matrices), deep nested lists, tikz-cd
commutative diagrams, mhchem chemistry, colortbl colour, multi-file `\input` chains,
fancyvrb/verbatim, a manual numeric `\bibitem` bibliography, advanced amsmath
(`\substack`/`\xrightarrow`/`multline`/`\boxed`), rotating `sidewaysfigure` + landscape
+ `\rotatebox`, a combined `\multirow`+`\multicolumn` cross-tabulation, biblatex
`\printbibliography` (biber), and marginalia (`\marginpar`/`\marginnote`/`\todo`).

- `python tests/run_tests.py` — for each fixture: latexmk-compile → `<name>_compiled.pdf`,
  run `convert.py --no-render` → `<name>.docx`, render via Word COM/soffice →
  `<name>_converted.pdf`, rasterize both, write `index.json`.
- `python tests/qa_metrics.py` — deterministic compiled-vs-converted text-diff metric
  (missing %, spurious-LaTeX count, table/figure/equation/unresolved counts) →
  `qa_metrics.json` + a summary table.

Current state: the corpus CONVERGES — 33 OK (≤~2.5% missing), 13 benign FLAG (<8%,
all explained: two-column/multicol linearization, biblatex hyphenation / page-number
formatting, a Word-COM render/extract transient, and figures-and-formulae-rendered-as-
images or Unicode sub/superscripts whose glyphs a text-diff metric cannot read back);
spurious 0 and unresolved 0 across all 46.
**Fix the converter (`scripts/`), never the fixtures** — the `tests/` corpus is the
scoring-adjacent ground truth. The corpus ships source `.tex` fixtures only; compiled
PDFs, rendered PNGs, and `.docx` artifacts regenerate on each run.

## Dependencies

- `pandoc` (3.x), `python-docx`, `pymupdf` (fitz), `Pillow`, `lxml`.
- A TeX install (`latexmk`/`pdflatex`) with `standalone.cls`, `preview.sty`, and the
  document's graphics packages — required only for TikZ/PGFPlots/algorithm rendering.
- Rendering: Microsoft Word (COM, via `win32com`) preferred; LibreOffice `soffice`
  fallback (`--headless --convert-to pdf`).
- The document's body font installed for Word/LibreOffice.

## Limitations

- Targets academic manuscripts (booktabs tables, cleveref, footnote citations,
  amsmath). TikZ/PGFPlots/algorithm floats are rendered as embedded images (faithful
  but not natively editable in Word, and their text is image pixels). Very exotic
  packages or non-booktabs table styles may still need per-document handling.
- Page breaks differ from the PDF (Word reflows); fidelity is element-level, not
  page-locked. Figure images are bound to their captions (keep-with-next) so a
  figure never splits from its caption, but long native tables may still break
  across pages (usually desirable).
- Author placeholders / `\input` of external content that is not a table or figure
  pass through as-is.

## References

- pandoc Manual — LaTeX reader & docx writer (reference-doc, footnotes, math/OMML).
- python-docx — tables, runs, styles; OOXML `w:tcBorders`, `w:vMerge`, `w:vertAlign`.
- booktabs package — rule weights and `\cmidrule` semantics.
- standalone / preview packages — compiling a single environment to a cropped PDF.

## Ported from tex2docx (2026-07-03)

When the `tex2docx` skill was retired, its pandoc-postprocessing fix registry was
diffed against this engine. Six of its seven fixes were already subsumed
architecturally (this engine prevents upstream what tex2docx patched after the fact),
so only the two genuine gaps were ported into the fidelity engine:

- **Notes punctuation normalizer** (`normalize_note_text` in `tex_table_to_docx.py`).
  Applied to table-notes text in BOTH table engines (estout / `tex_table_to_docx.py`
  and full-tabular / `full_tabular_to_docx.py`) so `\begin{tablenotes}` /
  threeparttable note punctuation is normalized consistently.
- **`\include{}` expansion** in `expand_latex_inputs`. Alongside the existing
  `\input{}` handling, `\include{}` is now expanded so multi-file manuscripts that
  split body content across `\include`d chapters are flattened before the body pass.

Deliberately NOT ported:

- **`\thanks`-symbol rendering (`* † ‡ §`).** tex2docx rendered footnote-symbol
  title notes with the classic LaTeX symbol series. This engine instead neutralizes
  `\author\thanks` (so body footnotes start at 1) and emits the thanks content as an
  "Author note:" paragraph — a different, deliberate design choice, not a gap.
- **tex2docx's `verify.py` structural counts.** Superseded by `tests/qa_metrics.py`,
  which performs a deterministic compiled-vs-converted text-diff over the 46-fixture
  corpus rather than raw structural counts.
- **The pandoc-damage fixes.** Architecturally impossible to need here: tables,
  figures, and captions are extracted to placeholders and built natively (or rendered
  to images), so they never pass through pandoc, which means the damage tex2docx
  repaired downstream never occurs in the first place.
