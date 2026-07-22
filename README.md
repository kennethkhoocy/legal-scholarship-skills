# legal-scholarship-skills

Claude Code and Codex skills for legal scholarship: verified citation placement and
restyling (Bluebook, OSCOLA, Chicago, APA, McGill), article planning,
document-driven literature discovery and screening, law-review manuscript
workflows in Word and LaTeX, and document sourcing and delivery.

Each skill is a self-contained folder that teaches
[Claude Code](https://docs.anthropic.com/en/docs/claude-code) or
[Codex](https://developers.openai.com/codex/) a workflow.
Install the whole set in either agent or copy individual skill folders — every
skill stands alone, with no cross-skill dependencies. A standalone Windows app
in `tools/cite-restyle/` exposes the citation-restyle pipeline to colleagues
who use neither Claude Code nor Codex.

## Contents

- [What this repository is for](#what-this-repository-is-for)
- [How the skills fit together](#how-the-skills-fit-together)
- [The skills](#the-skills)
  - [1. Citations](#1-citations) — [cite-placement](#cite-placement)
  - [2. Planning and drafting](#2-planning-and-drafting) — [writing-article-plans](#writing-article-plans)
  - [3. Manuscript exchange and editor workflows](#3-manuscript-exchange-and-editor-workflows) — [word-docx](#word-docx), [latex-to-word](#latex-to-word)
  - [4. Sources and delivery](#4-sources-and-delivery) — [lit-review-orchestrator](#lit-review-orchestrator), [pdf](#pdf), [download-gated-pdfs](#download-gated-pdfs), [markdown-to-pdf](#markdown-to-pdf)
- [Quick start: four scenarios](#quick-start-four-scenarios)
- [The standalone citation-restyle app](#the-standalone-citation-restyle-app)
- [Installation](#installation)
- [Requirements](#requirements)
- [Responsible use](#responsible-use)
- [Platform notes](#platform-notes)
- [License](#license)

## What this repository is for

Legal scholarship has a distinctive production pipeline: the argument is
carried substantially in footnotes, citation form is governed by demanding
style manuals, and delivery runs through Word-centric law-review editorial
processes even when the author drafts in LaTeX. The skills in this repository
instrument that pipeline for Claude Code and Codex — from planning an article's
structure, through placing and restyling verified citations, to surviving
rounds of editor redlines and delivering clean files in whatever format a
journal demands.

The repository leads with `cite-placement`. The most public AI failures in law
have been fabricated citations, and this skill is built as the answer to that
objection: it places citations **only from a user-supplied, pre-screened
bibliography**, verifies every reference against OpenAlex/CrossRef, and
deliberately leaves case citations untouched when restyling. Around it sit the
planning skill, the Word/LaTeX manuscript machinery, and the sourcing and
delivery plumbing.

## How the skills fit together

The skills map onto the stages an article actually passes through. None of
them requires another — each installs and runs alone — but together they cover
the pipeline end to end.

**Plan.** `writing-article-plans` interviews the author to settle the thesis,
contribution, article type, and structure, then writes a task-decomposed plan
in which every section is broken into paragraph-sized argument moves and every
claim needing support carries a typed citation slot rather than an invented
reference. Drafter subagents write the manuscript in LaTeX from the plan alone.

**Source.** Literature discovery precedes document retrieval:
`lit-review-orchestrator` works from a manuscript, abstract, or proposal to find
and screen the relevant sources into a verified, relevance-ranked bibliography.
Once the sources are identified, `download-gated-pdfs` retrieves the actual PDF
binary from bot-gated hosts — SSRN mirrors, think-tank sites — that serve an
HTML interstitial to non-browser clients, and `pdf` extracts the content once
the file exists, with a footnote-aware path for law-review articles that inlines
each footnote at its reference point instead of jumbling notes into the body.

**Cite.** With a draft in hand and a screened bibliography assembled,
`/cite-placement` places each reference where it belongs — as formatted
footnotes in one of five legal and notes styles, or as inline author-date
citations — and verifies every entry against bibliographic databases. When a
manuscript changes venue, its restyle mode converts the existing footnotes to
the new style while leaving case citations and legislation untouched.

**Survive editing.** Law reviews and co-authors work in Word. `word-docx`
reads the redlined `.docx` an editor returns and builds response-to-comments
documents or applies the author's replies as tracked edits, while
`latex-to-word` runs the round-trip for LaTeX authors — `.docx` to `.tex`,
edit, convert back — with a footnote-count check guarding against silent loss.

**Deliver.** At acceptance, `latex-to-word`'s one-way fidelity engine produces
a native Word file from the LaTeX source — real tables, real equations, real
footnotes — for Word-only journals, and `markdown-to-pdf` turns Markdown
memos, cover letters, and reports into polished PDFs.

## The skills

### 1. Citations

| Skill | Role |
|---|---|
| [`cite-placement`](plugins/legal-scholarship/skills/cite-placement/) | The flagship: places pre-screened citations into `.tex` or `.docx` manuscripts as formatted footnotes or inline cites, verifies them against bibliographic databases, and restyles existing footnote citations between legal styles. |

#### cite-placement

Places citations an author has already gathered and screened into a LaTeX or
Word manuscript, or restyles the citations a manuscript already has. A Tkinter
launcher collects the inputs and selects the mode; a placement run then maps
the manuscript at the paragraph level, ingests the spreadsheet of screened
references into BibTeX, plans where each citation belongs using parallel
sub-agents, inserts the citations into a new copy of the manuscript, and
compiles. The original file is never modified.

**Activation:** manual only. Type `/cite-placement` in Claude Code, mention
`$cite-placement` in Codex, or ask for the skill by name. It deliberately does
not auto-trigger on general citation or footnote requests, so a placement run
is always an explicit decision.

Key capabilities:

- **Three modes.** *Inline placement* writes `\cite{}` / `\citet{}` /
  `\citep{}` commands with a compiled `references.bib`, for author-date
  journals (APA, MLA, Harvard, Chicago author-date, IEEE, Vancouver; `.tex`
  only). *Footnote placement* writes full formatted `\footnote{}` in LaTeX or
  native OOXML footnotes in Word. *Restyle* converts every existing footnote
  citation from one style to another, with no spreadsheet required.
- **Five legal and notes styles**, selected with one click: Bluebook
  (21st ed.), OSCOLA (4th ed.), Chicago notes (17th ed.), APA (7th ed.), and
  McGill (9th ed.).
- **Short-form post-processing.** *Id.*, *supra* note N, *ibid*, and OSCOLA's
  `(n N)` cross-references are generated and kept consistent, including after
  manual edits (a `reorder_crossrefs.py` utility repairs them).
- **Verification.** An optional pass checks each reference against OpenAlex
  and CrossRef, with Google Scholar as an additional cross-check when an API
  key is configured, and flags dangling keys and entries it cannot confirm.
- **Restyle boundaries.** Journal-article, book, and working-paper citations
  are converted; signals, author formatting, and punctuation follow the target
  style. Case citations, legislation, and discursive footnotes are preserved
  byte-for-byte, and a changelog records every decision.
- **Utilities.** Strip all placed citations; regenerate or reorder
  cross-references; migrate legacy footnotes into the skill's marker scheme.

**Requirements:** Python 3.10+ with `openpyxl`; `python-docx`, `lxml`, and
`pydantic` for `.docx` manuscripts; a LaTeX distribution (`pdflatex` +
`bibtex`/`biber` for inline mode, `xelatex` for footnote and restyle modes);
network access for verification.

### 2. Planning and drafting

| Skill | Role |
|---|---|
| [`writing-article-plans`](plugins/legal-scholarship/skills/writing-article-plans/) | Interviews the author, gets a skeleton approved, and writes a task-decomposed article plan that drafter subagents execute section by section in LaTeX; a revision mode restructures existing drafts. |

#### writing-article-plans

Turns a research idea — or an existing draft — into a detailed `.md` plan
concrete enough that a drafter with no prior context can realize each argument
move as a paragraph. The skill interviews the author one question at a time to
settle the thesis, contribution, article type, evidence in hand, and target
venue; shows a section skeleton for approval; and only then expands it into
per-section move blocks, backed by an argumentative spine of load-bearing
claims. Genre structural profiles extracted from exemplar manuscripts
(empirical, theory, law review) drive section proportions, the introduction's
move template, and the footnote architecture.

**Activation:** automatic. Triggers on planning requests such as "plan this
paper", "an article plan", or "a paper outline to draft from", and in revision
mode when the author asks to restructure or substantively revise an existing
draft.

Key capabilities:

- **Interview-gated planning.** The plan is not written until the thesis and
  article type are settled; the approved skeleton is the cheap place to fix a
  wrong through-line.
- **Citations as typed slots.** The skill never runs a web search and never
  invents a reference; claims needing support are marked
  `% CITE: <kind of source needed>` for a later, verified placement pass.
- **Revision mode.** An existing draft is inventoried and diffed against the
  genre profile; every source section receives exactly one disposition —
  KEEP, REVISE, MERGE, SPLIT, NEW, or CUT — and kept text, existing citations,
  and existing numbers are carried through verbatim.
- **Auditable decisions.** A prompt-and-choices companion file records the
  initial spec verbatim and every interview question with the option chosen,
  so each plan is reproducible.
- **Drafter handoff.** One fresh subagent per section drafts the `.tex` from
  its move block; an assembly script flattens the sections into one
  parser-safe manuscript, and an optional cross-model red-team gate attacks
  the plan's thesis and spine before drafting begins.
- **Self-sufficient as shipped.** The pipeline ends with the drafters' prose,
  which is written to delivery quality. A separate style-emulation stage can
  extend the chain where such a skill is installed, but that is an optional
  external extension and is not part of this repository.

**Requirements:** Claude Code or Codex for planning. A LaTeX distribution
compiles the drafted output; the Codex CLI is optional for the red-team and
conformance gates.

**Example:** "Plan this paper — here is my abstract and the two tables I have
computed so far."

### 3. Manuscript exchange and editor workflows

| Skill | Role |
|---|---|
| [`word-docx`](plugins/legal-scholarship/skills/word-docx/) | The Word workhorse: extracts comments and tracked changes, builds response-to-comments documents, applies tracked edits via OOXML, and constructs new Word documents with native footnotes. |
| [`latex-to-word`](plugins/legal-scholarship/skills/latex-to-word/) | Moves manuscripts between LaTeX and Word: a footnote-preserving round-trip for co-author cycles and a high-fidelity one-way engine for delivering finished papers to Word-only journals. |

#### word-docx

A unified CLI for Microsoft Word `.docx` review and generation. Its design
principle is that the model never parses raw OOXML: every workflow first
extracts structured JSON and Markdown from the document, reasons over that,
and then builds a new `.docx` — the source file is never modified in place.
This is the skill that absorbs a law review's redline round.

**Activation:** automatic, whenever a task involves reading, reviewing,
building, editing, or analyzing `.docx` files.

Key capabilities:

- **Redline intake.** `extract-comments` and `extract-revisions` pull reviewer
  comments and tracked changes with author and date metadata, under stable IDs
  (C001…, R001…); `inspect` runs the full extraction and an OOXML audit in one
  pass.
- **Response-to-comments documents.** A build spec maps each comment to a
  response and a revision description, and the `build` command produces the
  response document — with proper OOXML footnotes generated from `[^N]`
  markers.
- **Tracked and silent edits.** `apply-edits` writes real `w:ins` / `w:del`
  elements through direct OOXML manipulation, auto-detecting whether the
  document already carries tracked changes, with the anchoring pitfalls that
  cause silent misfires documented for pre-validation.
- **Comment threads.** Reply to an existing comment, anchor a new comment on a
  text span, or mark a comment resolved.
- **Document construction.** New Word documents from JSON specs, including
  tables of contents, multi-column layouts, and page-numbered headers and
  footers via a Node-routed build path.
- **Hygiene commands.** Validation with auto-repair, accepting all revisions,
  legacy `.doc` conversion, unpack/repack, redline simplification, and
  rendering to PDF or images.

**Requirements:** Python with `docx2python`, `docx-revisions`, `python-docx`,
`docxtpl`, and `lxml`. Some commands subprocess to the Anthropic
document-skills plugin; TOC and column builds need Node ≥ 18 with the `docx`
package; `render-pdf` needs LibreOffice. Missing backends raise a clear error
naming the exact install command.

#### latex-to-word

Converts academic manuscripts between LaTeX and Word in either direction, in
three workflows. Workflow B, the default for delivery, is a high-fidelity
one-way `.tex → .docx` engine: it builds native Word tables from booktabs and
regression-table sources, converts math to OMML equations, produces real Word
footnotes, embeds figures, and resolves `\cref`/`\Cref`/`\eqref` from the
compiled `.aux` — the constructs plain pandoc drops or mangles. Workflow A is
the round-trip for iterating with Word-based co-authors (`.docx → .tex`, edit,
convert back, with a footnote-count sanity check and a GUI that drives the
cycle); workflow C is a set of knowledge patterns for assembling a single
`.tex` from mixed PDF, `.docx`, and LLM-generated sources.

**Activation:** automatic, on conversion requests in either direction
("convert to Word", "tex to docx", "convert this manuscript to LaTeX") and on
fidelity problems where pandoc alone loses tables or cross-references.

Key capabilities:

- Native Word tables, OMML equations, embedded figures, and resolved
  cross-references in the one-way engine, verified by a 46-fixture regression
  harness.
- A version-aware round-trip (`input/ intermediate/ output/` layout) that
  preserves footnotes across the docx–tex–docx cycle.
- TikZ, PGFPlots, and algorithm environments rendered through a real LaTeX
  pass rather than approximated.
- Escaping and Unicode patterns for building `.tex` from heterogeneous sources
  without brace-matching runaways.

**Requirements:** `pandoc` (3.x for the engine, ≥ 2.11 for the round-trip);
`xelatex`/`latexmk` from TeX Live or MiKTeX; `python-docx` and `lxml`.
Optional: PyMuPDF and Pillow for QA rasterization; Microsoft Word (COM) or
LibreOffice for a final render check. One documented caution: the GUI's
auto-edit and auto-fix loops invoke the Claude CLI with permission prompts
disabled — review that section of the skill's README before enabling them.

### 4. Sources and delivery

| Skill | Role |
|---|---|
| [`lit-review-orchestrator`](plugins/legal-scholarship/skills/lit-review-orchestrator/) | Document-driven literature-review pipeline: extracts a search plan from a manuscript, abstract, or proposal, runs several deep-search engines, then merges, deduplicates, verifies, and screens the results into a relevance-ranked bibliography. |
| [`pdf`](plugins/legal-scholarship/skills/pdf/) | Probe-first PDF extraction and manipulation, with a footnote-aware path built for law-review articles and GPU OCR for scans. |
| [`download-gated-pdfs`](plugins/legal-scholarship/skills/download-gated-pdfs/) | Retrieves the actual PDF binary from bot-gated sites via the Wayback Machine's raw-content endpoint. |
| [`markdown-to-pdf`](plugins/legal-scholarship/skills/markdown-to-pdf/) | Converts Markdown to a polished PDF with every image embedded, scaled, and verified. |

#### lit-review-orchestrator

Runs a literature-review pipeline from a document that describes the article
rather than from a hand-typed query. Given a `.tex` or `.docx` — a full
manuscript, an abstract, or a proposal — it extracts a search plan (the research
question, channel-specific briefs, and a query list), searches several
deep-research engines concurrently, then merges, deduplicates, verifies, and
screens the candidates into a relevance-ranked bibliography delivered as a
spreadsheet alongside RIS and BibTeX. Verification is the design center: every
candidate is cross-checked against OpenAlex, Crossref, or Semantic Scholar, and
any reference no index can confirm is dropped to a separate audit file, which
removes the fabricated-citation failure mode that language-model literature
search would otherwise introduce.

**Activation:** manual-invoke only. Type `/lit-review-orchestrator` in Claude
Code, mention `$lit-review-orchestrator` in Codex, or ask for it by name; the
skill deliberately does not auto-trigger on general literature-review
requests, so a search run is always an explicit decision.

Key capabilities:

- **Document-driven search planning.** Stage 0 reads the manuscript or abstract
  and derives the research question, an Undermind brief, a Scholar Labs
  question, and a Google Scholar query list, so the search reflects the
  article's content instead of a keyword string typed by hand.
- **Several deep-search engines fused into one list.** Undermind, Gemini Deep
  Research, and Google Scholar (via SearchAPI.io) run concurrently, with opt-in
  Google Scholar Labs, SSRN, NBER, HeinOnline, and Semantic Scholar citation
  chaining; the results are merged, enriched, and deduplicated by DOI and an LLM
  fuzzy pass.
- **Verification by default.** Stage 5b confirms each paper against three
  scholarly indexes and drops what none can confirm, distinguishing an index
  outage from a genuinely absent paper so that a network failure never deletes
  real work. `--no-verify` disables it.
- **Agent-layer reasoning with no Anthropic API key.** Plan extraction, dedup
  judgments, relevance screening, and the keyless web search run at the agent
  layer through an emit/ingest seam; an autonomous fallback on the
  Sonnet/DeepSeek API covers unattended runs.
- **Ranked, screened output.** What survives verification is scored for
  relevance against the research question and written as a ranked spreadsheet,
  RIS, and BibTeX, with a score-filtered shortlist.

**Terms-of-service caution.** The Undermind stages automate a logged-in browser
session against Undermind, a paid service with no public API, under your own
paid account. Automated access may sit outside Undermind's terms of service, so
these stages are used at your own risk under your own account. The pipeline does
not depend on them: when the Undermind credentials are absent or its login is
declined, the stage defers and the run continues on the other channels,
including the keyless web search and free-index search that need no account.

**Requirements:** Python 3.10+ with the packages in the skill's
`requirements.txt`, and Playwright with Chromium (`playwright install chromium`)
for the browser-driven Undermind and Scholar Labs stages. An Undermind account
is needed for the Undermind stages and a SearchAPI.io key for the Google Scholar
stage; `GEMINI_API_KEY` enables Gemini Deep Research, while optional
`DEEPSEEK_API_KEY` and `OPENALEX_API_KEY` improve deduplication and metadata
enrichment. Verification and the two keyless channels use the free
OpenAlex/Crossref/Semantic Scholar pools, so the pipeline can run with no search
account at all.

#### pdf

One entry point for all PDF work, organized around a probe-first design: a
one-second classifier inspects the file and routes it to the cheapest
sufficient backend, from an instant `pypdf` text dump for simple born-digital
files up to GPU OCR for scans. The path that matters most for legal
scholarship is the footnote-aware extraction: for a footnote-bearing academic
paper, a Docling-based extractor inlines each footnote at its reference point
in the output — precisely what generic extractors jumble or drop on law-review
articles. A deterministic verification gate then flags merged table rows,
broken equations, and stray glyphs, with a render-and-rewrite repair loop for
anything it catches.

**Activation:** automatic, whenever a task mentions a `.pdf` file or asks to
produce one.

Key capabilities:

- Extraction routing across `pypdf`, `pdfplumber` (tables),
  `opendataloader-pdf` (complex layouts), and Docling (footnotes and formula
  LaTeX), driven by the probe's classification and overridable by user hints.
- OCR for scanned and photographed documents via LightOnOCR-2-1B (GPU, ~3 GB
  VRAM, LaTeX-aware), with dolphin v2 as fallback.
- Annotation extraction — reviewer comments, highlights, sticky notes — from
  the PDF annotation layer, which content extractors never see.
- General operations: merge, split, rotate, watermark, encrypt/decrypt, image
  extraction, and creation from scratch.

**Requirements:** the Python PDF stack per its README (`pypdf`, `pdfplumber`,
and friends); `opendataloader-pdf` and Docling for complex layouts; optional
locally installed OCR models for scanned documents.

**Example:** "Extract the text of this law-review article and keep the
footnotes attached to the sentences they annotate."

#### download-gated-pdfs

Solves a narrow, recurring problem: a `.pdf` URL on a think-tank, publisher,
or SSRN-mirror site returns an HTML bot-challenge page instead of the file,
even with a browser User-Agent, so the "PDF" on disk fails to parse. The skill
requests the file through the Wayback Machine's raw-content (`id_`) URL form,
which serves the original archived binary without rewriting, then verifies the
download by opening it with `pypdf` and checking the page count. Government
data hosts are usually ungated, so a direct fetch remains the first attempt;
the Wayback route is the fallback for hosts that block it.

**Activation:** automatic, on the failure signature — a downloaded "PDF" that
starts with `<!DOC`, or `pypdf` raising `invalid pdf header` on a fresh
download.

**Requirements:** none beyond `curl` and `pypdf`.

#### markdown-to-pdf

Converts GitHub-flavored Markdown to a PDF that looks like the rendered
document the author reviewed. Because pandoc's default LaTeX route breaks on
real-world Markdown, the skill instead renders to standalone HTML with every
local and remote image embedded as a data URI, prints with headless Chrome
under a GitHub-like stylesheet that scales each image to the page, and
verifies with `pypdf` that every referenced image made it into the output.
Useful for memos, reports, and anything a colleague wants as one polished file.

**Activation:** automatic, on requests to save, convert, or export a `.md`
file as a PDF.

**Requirements:** `pandoc`, a Chrome/Edge/Chromium binary, and `pypdf`.

**Example:** "Save `submission-memo.md` as a PDF for the dean's office."

## Quick start: four scenarios

Concrete situations, each resolved with one skill. All assume the plugin is
installed (see [Installation](#installation)).

**A law review returns a redlined `.docx`.** Say: "Summarize the comments and
tracked changes in `article_redline.docx`, then draft a response-to-comments
document." `word-docx` triggers, extracts every comment and revision to
structured JSON with stable IDs, and builds a response document pairing each
comment with your reply and the revision made. When you decide which edits to
accept, it applies them as tracked changes the editors see natively in Word.

**Footnotes must convert from Bluebook to OSCOLA.** A US-drafted piece is
going to a UK journal. Type `/cite-placement`, pick the manuscript in the
launcher, set Bluebook → OSCOLA, and click Restyle. Every journal-article,
book, and working-paper footnote is reformatted; *supra* note N becomes
`(n N)`; case citations, legislation, and discursive footnotes pass through
untouched; a changelog records each conversion for review.

**A Word-only journal demands delivery of a LaTeX manuscript.** Say: "Convert
`main.tex` to Word for submission — tables, equations, and cross-references
must survive." `latex-to-word` compiles once so a current `.aux` exists, then
runs its fidelity engine: regression tables become native Word tables, math
becomes OMML equations, footnotes become real Word footnotes, and `\cref`
references resolve to their printed numbers.

**A gated SSRN or think-tank PDF will not download.** The fetched file turns
out to be an HTML challenge page. `download-gated-pdfs` recognizes the
signature, pulls the original binary through the Wayback Machine's `id_`
endpoint, and verifies it opens with a plausible page count; the `pdf` skill
then extracts the article's text with its footnotes inlined where they belong.

## The standalone citation-restyle app

`tools/cite-restyle/` contains the source of a standalone Windows app exposing
`cite-placement`'s restyle pipeline to colleagues who use neither Claude Code
nor Codex:
select a manuscript, choose the current and target styles, and run. The app is
built from this source with PyInstaller using the bundled `.spec` file.

Prebuilt binaries, when distributed, appear only as GitHub Release assets and
are never committed to the repository. The executable is unsigned, so Windows
SmartScreen will warn on first launch; that caveat, and how to proceed past
it, is documented in the tool's own README.

## Installation

### Claude Code plugin

```
/plugin marketplace add kennethkhoocy/legal-scholarship-skills
/plugin install legal-scholarship@legal-scholarship-skills
```

### Codex

Clone the repository, then copy its skill folders into Codex's user
skill directory:

```bash
git clone https://github.com/kennethkhoocy/legal-scholarship-skills
mkdir -p ~/.agents/skills
cp -R legal-scholarship-skills/plugins/legal-scholarship/skills/. ~/.agents/skills/
```

On Windows PowerShell, replace the last two commands with:

```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills"
Copy-Item -Recurse -Force "legal-scholarship-skills\plugins\legal-scholarship\skills\*" "$HOME\.agents\skills\"
```

Codex also supports symlinked skill folders. If a per-skill example uses
`~/.claude/skills/`, substitute `~/.agents/skills/` when running it in Codex.

### Manual Claude Code install

```
git clone https://github.com/kennethkhoocy/legal-scholarship-skills
# copy the skill folders you want from plugins/legal-scholarship/skills/
# into ~/.claude/skills/ — every skill is self-contained; no sibling
# folders required.
```

Six of the eight skills trigger automatically when a task matches their
description; the per-skill sections above state each trigger. `cite-placement`
and `lit-review-orchestrator` are the exceptions — use `/skill-name` in Claude
Code or mention `$skill-name` in Codex. This is a deliberate design choice so
that citation placement and literature searches never happen as a side effect.

## Requirements

Every skill runs inside Claude Code or Codex; the table lists what else each
one needs. Entries marked *optional* enable a specific capability and can be
skipped otherwise.

| Skill | Python packages | External tools | Optional |
|---|---|---|---|
| `cite-placement` | 3.10+, `openpyxl`; `python-docx`, `lxml`, `pydantic` for `.docx` | LaTeX distribution (`pdflatex`+`bibtex`/`biber` inline; `xelatex` footnotes/restyle) | Google Scholar cross-check via a SearchAPI key; OpenAlex/CrossRef need network access |
| `writing-article-plans` | none | none for planning; LaTeX to compile the drafted output | Codex CLI for the plan red-team and section-conformance gates |
| `word-docx` | `docx2python`, `docx-revisions`, `python-docx`, `docxtpl`, `lxml` | none for the core commands | Anthropic document-skills plugin (validate, accept-changes, `.doc` conversion, redline simplification); Node ≥ 18 + `docx` package (TOC/column builds); LibreOffice (`render-pdf`) |
| `latex-to-word` | `python-docx`, `lxml` | `pandoc` (3.x engine; ≥ 2.11 round-trip); `xelatex`/`latexmk` | PyMuPDF + Pillow (QA rasterization); Word COM or LibreOffice (render check) |
| `lit-review-orchestrator` | 3.10+, the packages in the skill's `requirements.txt` | Playwright + Chromium (`playwright install chromium`) for the browser-driven Undermind and Scholar Labs stages | Undermind account for the Undermind deep-search stages (automated, at your own risk under Undermind's terms); SearchAPI.io key for Google Scholar; `GEMINI_API_KEY` for Gemini Deep Research; `DEEPSEEK_API_KEY`/`OPENALEX_API_KEY` for dedup and enrichment; the keyless web and free-index channels need no account |
| `pdf` | `pypdf`, `pdfplumber` | `opendataloader-pdf` + Docling for complex layouts | local GPU OCR models (LightOnOCR-2-1B, ~3 GB VRAM; dolphin fallback); `qpdf`, `reportlab`, PyMuPDF for manipulation and annotations; Node for KaTeX math validation |
| `markdown-to-pdf` | `pypdf` | `pandoc`; Chrome, Edge, or Chromium | per-job CSS overrides need nothing extra |
| `download-gated-pdfs` | `pypdf` | `curl` | none |

The minimal install and the full stack differ considerably. With Python and a
handful of pip packages you already have the Word review workflow, gated-PDF
retrieval, basic PDF extraction, and article planning — enough for an author
who works mainly in Word. The full stack adds `pandoc` and a LaTeX
distribution (which unlock the LaTeX–Word conversions and `cite-placement`'s
compile steps), a Chromium-family browser for PDF printing, LibreOffice and
Node for `word-docx`'s outer capabilities, GPU OCR models only for scanned
documents, and the Codex CLI only for `writing-article-plans`' cross-model
review gates. Each skill degrades cleanly, naming the missing backend and its
install command, so start minimal and add tools when a workflow asks for them.

## Responsible use

Citation integrity is the design center of this repository. `cite-placement`
places citations only from a bibliography you supply and screen; it verifies
every reference against OpenAlex/CrossRef, and it cannot fabricate a source,
because it has no path that generates one — its role is deciding where an
existing, screened reference belongs and formatting it correctly. During
restyling it rewrites formatting only, leaving case citations, legislation,
and discursive footnotes untouched, so no substantive citation content is
altered or introduced.

`writing-article-plans` heads a drafting pipeline: the thesis, argument
structure, and every structural decision in the plan are the author's,
captured through an interview and approved explicitly, and the drafting agents
then generate prose from that plan. Machine-generated prose is exactly what
most journal AI policies ask authors to disclose. Use the skill with your
journal's disclosure policy in hand; the plan you approve is yours, and so is
responsibility for the draft that realizes it.

## Platform notes

The skills were developed on Windows. Most code is cross-platform Python, and
the conversion pipelines depend only on tools (`pandoc`, TeX, Chrome,
LibreOffice) that exist on every platform; exceptions are flagged in the
individual skill READMEs. Two skills ship GUI launchers (`cite-placement`'s
Tkinter launcher and `latex-to-word`'s round-trip GUI), which need a desktop
session and a Python with Tkinter available; both skills also expose script
entry points that run without the GUI. The standalone cite-restyle executable
is Windows-only as released, though its source is portable Python.

A companion repository,
[`applied-micro-skills`](https://github.com/kennethkhoocy/applied-micro-skills),
carries the empirical-research toolchain (reproducibility auditing,
LLM-classification methods, event studies, WRDS/Stata infrastructure). Five
skills — `cite-placement`, `latex-to-word`, `markdown-to-pdf`,
`download-gated-pdfs`, and `lit-review-orchestrator` — ship in both
repositories, because empirical legal scholarship draws on both toolchains at
once.

## License

MIT. See [`LICENSE`](LICENSE).
