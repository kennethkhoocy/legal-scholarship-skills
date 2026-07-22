# writing-article-plans

A Claude Code skill that turns a research idea into a detailed, task-decomposed
`.md` plan for an academic article, which a separate drafter agent then writes
section by section in LaTeX. It is the academic-writing counterpart of a
design-then-build workflow: the skill interviews the author to settle intent,
gets approval on a section skeleton, and only then expands that skeleton into a
plan concrete enough that a drafter with no prior context can realize each
argument move as a paragraph.

The plan carries the whole argument down to individual moves, so the manuscript
that follows realizes a decided argument rather than improvising one. Structure
is treated as the first-order decision, because a downstream pass can improve
prose but cannot restructure a draft.

## What it produces

Two Markdown files on disk:

- **The article plan** (`docs/plans/YYYY-MM-DD-<slug>-article-plan.md`) — the
  deliverable. It records the thesis, the contribution, an argumentative spine of
  load-bearing claims, an evidence inventory, a file layout for the `.tex`
  sources, and one block per section giving the drafter its role, the claims it
  realizes, its structural notes, and a checklist of paragraph-sized moves.
  Citations appear only as typed slots (`% CITE: <kind of source needed>`); the
  skill never runs a web search and never invents a reference.
- **A prompt-and-choices companion** (`...-prompt-and-choices.md`) — the initial
  spec verbatim together with every interview question and the option chosen, so
  each plan is reproducible and its decisions are auditable.

The manuscript the drafter later writes is LaTeX (`main.tex` plus
`\input{sections/<name>.tex}`), which drops into a standard LaTeX results
pipeline.

## How it works

The skill runs as a gated sequence:

1. **Interview.** It asks one question at a time — thesis, contribution and gap,
   article type, evidence in hand, target venue and length, framing, constraints
   — reading whatever spec, notes, or existing manuscript the author supplies
   first, and asking only what is genuinely open. The thesis and the article type
   must be settled before any plan is written.
2. **Skeleton approval.** It shows the thesis, the argumentative spine, and a
   one-line-per-section outline in the chat, names the structural profile it will
   follow, and flags any deviation from it. The author approves the structure
   before expansion, which is the inexpensive place to correct a wrong
   through-line.
3. **Plan expansion.** It writes the full per-section move blocks to the plan
   file, then writes the prompt-and-choices companion beside it.
4. **Self-review and red-team.** It rereads the plan against the spec, runs one
   cross-model red-team pass (described below), fixes any blocking findings, and
   reports the file paths for approval.

Drafting the manuscript is a separate step the author opts into once the plan
exists.

### Article types and structural profiles

The article type — `empirical`, `theory`, `law_review`, or `review` — selects a
structural profile stored under `references/genre-structures/<genre>/`. A profile
is extracted from an exemplar manuscript and records its section inventory and
proportions, its heading conventions, an ordered template for the introduction's
moves, each section's internal organization, and the footnote architecture. That
profile drives the section skeleton, the introduction scaffold, and the
per-section structural notes handed to the drafter. When a genre folder holds
several profiles, one is marked as the default and the others are offered when
the venue or structure is in question. A type with no profile falls back to a
built-in section list, noted in the plan header.

## Two modes

**New article.** No manuscript exists; the plan is built from a spec and drafted
from scratch.

**Revision.** A draft already exists and the author wants it restructured or
substantively revised — sections reorganized, the argument sharpened, or the
manuscript conformed to a genre structure. The draft serves two roles at once: it
is the specification of the argument already committed, and it is raw material to
preserve. Before the interview, the skill inventories the draft (its sections
with word shares, the moves each section makes, its evidence anchors, its
footnote layer) and diffs that against the target structural profile, so the
interview addresses the actual gaps. Every existing section then receives exactly
one disposition:

- `KEEP` — carried over verbatim; the drafter copies rather than rewrites.
- `REVISE` — the moves state what changes and what is retained.
- `MERGE` / `SPLIT` — with the affected sections named on both sides.
- `NEW` — drafted from scratch.
- `CUT` — with a note on where any salvageable content goes.

Existing real citations and numbers are carried through unchanged, and the
original file is never modified: the revision is drafted into a fresh `main.tex`
and `sections/` tree beside it.

## Standalone mode

The skill is self-sufficient. On a plain installation it produces the plan,
drafts the LaTeX, and hands off to citation placement downstream, which yields a
fully usable manuscript.

A separate `style-emulation` skill, when it happens to be installed, extends the
pipeline with a final stage that restyles the cited draft into a target authorial
voice. `style-emulation` is not part of this repository and is not required; most
installations will not have it. The skill detects its presence once at the start
of a run. In its absence — the standalone case — the plan header records the
restyle fields as `n/a (standalone)`, the drafters are told their prose is the
final prose and must reach delivery quality, and the downstream pipeline ends at
citation placement. When it is present, the skill records the chosen restyle
style and adds the restyle as the pipeline's final refinement.

## The plan red-team gate

Before the plan is shown to the author, the skill runs one substantive red-team
review on a different model family, which examines whether the argument is worth
building — the contestability of the thesis, the logic of the spine, and the
objections a hostile referee would raise. This pass is dispatched through the
**Codex CLI**, an optional dependency: the skill fills a bundled prompt template,
pipes it to `codex exec`, reads the result back, and fixes any blocking findings
in a single round. Where the Codex CLI is not installed, this cross-model gate is
skipped; the skill's own self-review still runs, and an optional in-repo
plan-completeness reviewer prompt remains available.

## Downstream pipeline

Once the plan is approved and the sections are drafted, the per-section `.tex`
files are assembled into one self-contained `combined.tex` by the bundled
`scripts/assemble_manuscript.py`, which inlines every `\input` and rewrites the
footnote citation slots into a parser-safe form. The assembled draft then moves
downstream:

1. **`lit-review-orchestrator`** — finds the literature for the article.
2. **`cite-placement`** — fills every `% CITE:` slot in the citation style and
   mode the structural profile implies, whether author-date in the body or
   citations carried in footnotes.
3. **`style-emulation`** *(only when installed)* — restyles the fully cited draft
   into the author's voice.

The first two are the standard downstream companions that turn a slots-only draft
into a cited manuscript; the third is the optional voice stage described above.
Each is a separate skill invoked in turn.

## Inputs

The typical input is a research proposal or an existing manuscript, although a
one-line topic, a research question, an abstract, rough notes, or a summary of
already-computed results all work as well. Markdown and LaTeX files are read
directly. Word `.docx` files are parsed through the companion `word-docx` skill
before planning, and the parsed text — never the `.docx` itself — becomes the
working source that revision-mode anchors point at.

## Bundled files

- `SKILL.md` — the full skill specification (the authoritative reference).
- `references/plan-template.md` — the annotated plan template and a worked
  micro-example; read this before writing a first plan.
- `references/genre-structures/<genre>/<name>.md` — structural profiles for the
  `empirical`, `theory`, and `law_review` genres, each extracted from an exemplar
  manuscript.
- `references/prompt-and-choices-example.md` — a worked example of the
  prompt-and-choices companion.
- `prompts/section-drafter.md` — the subagent prompt that drafts one section into
  `.tex` from its plan block.
- `prompts/plan-reviewer.md` — an optional plan-completeness reviewer prompt.
- `prompts/codex-plan-redteam.md` — the cross-model red-team prompt run before
  author approval.
- `prompts/codex-section-conformance.md` — an optional per-section cross-model
  check that a drafted section realizes its plan block.
- `scripts/assemble_manuscript.py` — flattens the per-section `.tex` files into
  one parser-safe `combined.tex`.

## Requirements

- **Claude Code**, which supplies the skill runtime, the interview tooling, and
  the drafter subagents.
- **Codex CLI** *(optional)* — enables the cross-model plan red-team gate;
  without it, that gate is skipped.
- **`word-docx` skill** *(optional)* — needed only to plan from a `.docx` input.
- **`lit-review-orchestrator` and `cite-placement`** — the downstream skills that
  find the literature and fill the citation slots; each is invoked after this
  skill rather than during it.
- **`style-emulation` skill** *(optional, external)* — adds the final restyle
  stage when installed; it is not part of this repository.

## Invocation

Ask Claude Code to plan, outline, structure, or scaffold a paper before drafting
— for example, "write a plan for this article," "give me a paper outline to draft
from," or "plan this paper." To restructure or substantively revise an existing
draft, ask for that explicitly ("revise / restructure this draft") so the skill
enters revision mode. The skill announces itself when it begins.

## Responsible use

This skill heads a drafting pipeline that generates manuscript prose from a plan
the author has reviewed and approved. Authorship stays with the author: the
interview settles the thesis and argument, the skeleton is approved before
expansion, and the plan forbids invented evidence, numbers, or citations. Authors
are responsible for complying with the AI-use and AI-disclosure policies of the
journals to which they submit, and those policies vary by venue and change over
time. Verify a target journal's current policy before submitting work produced
with this pipeline.
