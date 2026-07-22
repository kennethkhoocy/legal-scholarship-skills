# Article Plan — Full Template and Worked Example

This is the reference the `writing-article-plans` skill points to. The first half
is the annotated template; the second half is a short worked example so the shape
is concrete.

---

## Annotated Template

```markdown
# [Working Title] — Article Plan

> **For the drafter:** REQUIRED SUB-SKILL — dispatch a fresh section-drafter
> subagent per section (writing-article-plans → "Drafter Handoff"), or draft inline
> section-by-section. Write LaTeX. Realize the argument moves below; do not invent
> evidence, numbers, or citations beyond the typed slots. Checkboxes track progress.

**Mode:** new | revision
**Article type:** empirical | theory | law_review | review
**Restyle genre:** [review type only: which style-emulation genre the restyle borrows | n/a (standalone)]
**Restyle style:** [style-emulation `--spec` name | unpinned | n/a (standalone)]
**Structure profile:** references/genre-structures/<genre>/<name>.md | fallback table
**Source draft:** [absolute path, revision mode only]
**Target venue / length:** [field + approx. word count]
**Draft format:** LaTeX — main.tex with \input{sections/<name>.tex}
```

Header notes:
- **Article type** selects the structural profile and the `style-emulation`
  genre. Default to `empirical` unless the spec says otherwise. For `review`,
  which has no style-emulation genre, the Restyle genre line records which
  genre the eventual restyle borrows; other types omit that line. In standalone
  mode (no `style-emulation` installed) the genre mapping has no consumer, so
  the Restyle genre line, where present, reads `n/a (standalone)` — the
  structural profile the type selects still applies.
- **Restyle style** pins which of the genre's style specs the eventual restyle
  uses (style-emulation `--spec`), settled during the interview via
  `--styles --json` and its asking rule. `unpinned` defers to style-emulation's
  own resolution at restyle time. In standalone mode there is no restyle stage,
  so this line reads `n/a (standalone)` and the interview skips the pin.
- **Structure profile** names the candidate-manuscript profile the plan follows
  (see SKILL.md → "Genre Structural Profiles"). Section order, the intro move
  scaffold, and the footnote policy come from it; structural deviations are
  declared at skeleton approval. The profile's word shares are a soft guide to
  relative section weight — per-section targets are the planner's call for this
  article's length, and every word count in the plan is soft.
- **Mode / Source draft**: revision mode treats the named draft as the spec and
  as raw material; every section block then carries Disposition and Source
  material lines, and the preservation rules in SKILL.md → "Two Modes" bind the
  drafter. The original draft is never modified. For a `.docx` source, the
  Source draft line names both the original (provenance) and the word-docx
  parsed-text artifact, and every anchor points at the artifact.
- Keep the drafter blockquote verbatim — it is the drafter's contract.

```markdown
## Thesis
[One or two sentences stating the central claim the paper defends. If the user
has not committed to a thesis, stop and ask; do not invent one.]

## Contribution
[What is new; what gap it fills; why it matters. A few bullets, each a distinct
contribution, not restatements of one.]

## Argumentative spine
C1: [load-bearing claim] — evidence: [Tables/table_h1.tex | % CITE: … | logical]
C2: [claim that builds on C1] — evidence: …
C3: …
```

The spine is the paper's logical order, not necessarily the section order. Every
section move later cites the claim IDs it realizes, so an orphan claim (in the
spine, realized by no section) or an unsupported section (asserts a claim absent
from the spine) is visible at review time.

```markdown
## Claims register
| ID | Claim | Supported by | Appears in |
|----|-------|--------------|------------|
| C1 | …     | Table 2      | Intro, Results |

## Hypotheses            (empirical / theory only)
H1: [statement] → tested by [design/anchor] → result: [from spec, or
    "% RESULT: fill from Table 3"]

## Terminology
- [term] → [the exact definition to use everywhere; the drafter must not drift]

## Evidence inventory
- Tables / figures available (by anchor path or \label): …
- Citation slots (typed, no keys yet): [one line per claim needing a source]
- Results not yet computed: [mark as % RESULT slots; never fabricate]

## Source draft disposition map        (revision mode only)
| Source section | Disposition | Target section(s) / destination | Source anchor |
|----------------|-------------|--------------------------------|---------------|
| Old §5 Robustness | CUT | salvage: one paragraph → new §4 discussion; rest nowhere | old_draft.tex ¶61–70 |
```

The disposition map is the exhaustive per-source-section record — one row per
section of the source draft. It is where CUT and the source side of MERGE/SPLIT
live, since those have no target section block of their own; the target blocks'
Disposition lines are its section-level view.

```markdown
---

## File layout
- Create: main.tex                 (preamble; \input order matching spine flow)
- Create: sections/intro.tex
- Create: sections/data.tex
- …

---
```

```markdown
### Section N: [Name]  `sections/<name>.tex`   (~N words, soft)

**Role:** [what this section must accomplish in the spine — one sentence]
**Realizes claims:** C1, C3
**Structure notes:** [from the profile: the section's internal organization
(e.g., "table-by-table walk, each table introduced by the hypothesis it
tests"), footnote policy (law_review: which content goes to substantive
footnotes), required formal environments (theory: proposition/proof)]
**Disposition:** KEEP | REVISE | MERGE | SPLIT | NEW   (revision mode only;
CUT appears only in the Source draft disposition map — it has no target block)
**Source material:** [old draft section / ¶ range, or "none — NEW"]
**Opens from:** [prior section's end state / "cold open"]
**Hands to:** [what the next section assumes is now established]

- [ ] **Move 1 — [label].** [the actual content: the specific claim, puzzle,
      derivation step, or result — written out, not described]
- [ ] **Move 2 — [label].** [… with a typed citation slot where needed:
      `% CITE: study documenting the X effect`]
- [ ] **Move 3 — [label].** [each move is one paragraph the drafter can write
      from the move text alone]
- [ ] **Draft** sections/<name>.tex realizing Moves 1–N in LaTeX. Reference
      anchors by \ref/\input; do not redraw tables.
- [ ] **Verify:** every move present; claims [IDs] stated; citation slots marked;
      table/figure refs resolve; no invented numbers; Structure notes honored
      (internal organization, footnote placement, formal environments);
      (revision) Disposition honored — kept text verbatim, existing citations
      and numbers intact.
```

Repeat the section block for each file in `## File layout`.

Genre-structural move forms:

- **law_review:** a move may place part of its content in a substantive
  footnote with the inline marker `[substantive footnote: <the content>]`; the
  drafter writes that content as real `\footnote{...}` prose. Citation-only
  support stays a typed `% CITE:` slot. Which content belongs in substantive
  footnotes (counterarguments, doctrinal detail, asides) comes from the
  profile's footnote architecture.
- **theory:** a move that states a formal result names its environment and
  number ("state Proposition 2: <the claim>"); the drafter writes it in the
  actual `\begin{proposition}...\end{proposition}`, with the proof in
  `\begin{proof}` or the appendix as the profile directs.

Revision-mode section block (abbreviated example — a REVISE disposition):

```markdown
### Section 3: Identification  `sections/identification.tex`  (~1,400 words, soft)

**Role:** Establish the design before any result is shown.
**Realizes claims:** C2
**Structure notes:** per profile — the specification as a numbered display
equation before any table walk.
**Disposition:** REVISE (built from old Sections 5.1–5.2, moved ahead of Results)
**Source material:** old_draft.tex ¶41–52
**Opens from:** data section.   **Hands to:** results assume the specification.

- [ ] **Move 1 — Keep.** Retain ¶42–45 (the parallel-trends argument) verbatim,
      including its existing \cite keys.
- [ ] **Move 2 — Replace.** Rewrite the old opening ¶41, which assumed results
      already shown; open instead from the data section's sample definition.
- [ ] **Move 3 — Add.** State the estimating equation as a numbered display
      (it was prose in the old draft).
- [ ] **Draft** sections/identification.tex realizing the moves; copy kept text
      byte-for-byte; carry all existing citations through.
- [ ] **Verify:** kept ¶s verbatim; no citation dropped or slotted; equation
      numbered; Structure notes honored.
```

---

## What "No Placeholders" Means Here

| Failure | Fix |
|---------|-----|
| Move: "discuss prior work" | Move: "position against Smith (2019)'s null result, which our design overturns because …" |
| Move: "report the main result … the effect is about 8%" (invented) | Move: "report the main coefficient — `% RESULT: coef on treat, Table 3 col 2`" |
| `[cite]` | `% CITE: RCT evidence on take-up of Y` |
| Section 6 asserts C7, absent from spine | Add C7 to the spine with its evidence, or cut the assertion |
| (revision) An existing citation converted to a `% CITE` slot | Carry the existing \cite/footnote through verbatim; slots are for claims new to the revision |
| (revision) A section of the source draft with no disposition | Assign exactly one: KEEP/REVISE/MERGE/SPLIT/NEW/CUT (CUT names where salvage goes) |

---

## Worked Example (abbreviated)

```markdown
# Buyback Waves and Board Independence — Article Plan

> **For the drafter:** REQUIRED SUB-SKILL — dispatch a fresh section-drafter
> subagent per section … Write LaTeX. Realize the moves; invent nothing beyond slots.

**Mode:** new
**Article type:** empirical
**Structure profile:** references/genre-structures/empirical/expanding-shareholder-voice.md
**Target venue / length:** corporate-finance field journal, ~11,000 words
**Draft format:** LaTeX — main.tex with \input{sections/<name>.tex}

## Thesis
Firms with more independent boards time share buybacks to periods of temporary
undervaluation, and this timing ability, not a mechanical payout preference,
explains their higher post-buyback returns.

## Contribution
- Separates timing skill from payout preference, which prior work conflates.
- Uses board-independence shocks from the 2003 listing rules for identification.
- Documents that the return gap concentrates in high-information-asymmetry firms.

## Argumentative spine
C1: Independent-board firms buy back more after negative idiosyncratic shocks —
    evidence: Table 2 (event-time buyback intensity).
C2: Their post-buyback abnormal returns exceed those of other firms —
    evidence: Table 3 (CARs by board type).
C3: The gap is concentrated where asymmetry is highest —
    evidence: Table 4 (interaction).
C4: Payout-preference explanations do not survive the 2003-rule design —
    evidence: Table 5 (IV / diff-in-diff), % CITE: payout-smoothing literature.

## Hypotheses
H1: Board independence predicts buyback timing → tested by event-time intensity
    regressions → result: % RESULT: fill from Table 2.
H2: Timing drives the return gap → tested by asymmetry interaction → % RESULT: Table 4.

## Terminology
- "timing ability" → repurchasing disproportionately after transitory
  undervaluation, measured by post-event CARs; never used to mean market-wide timing.

## Evidence inventory
- Anchors: Tables/table_buyback_intensity.tex, Tables/table_cars.tex,
  Tables/table_interaction.tex, Tables/table_iv.tex; \ref{fig:eventwindow}.
- Citation slots: payout-smoothing literature (C4); board-independence/監督 role.
- Results not computed: none — all four tables exist.

---

## File layout
- Create: main.tex        (\input intro, data, methodology, results, discussion, conclusion)
- Create: sections/intro.tex
- Create: sections/data.tex
- Create: sections/methodology.tex
- Create: sections/results.tex
- Create: sections/discussion.tex
- Create: sections/conclusion.tex

---

### Section 1: Introduction  `sections/intro.tex`  (~1,200 words, soft)

**Role:** Establish the puzzle, the identification idea, and the headline finding.
**Realizes claims:** C1, C2, C4
**Structure notes:** intro architecture per profile — puzzle, gap, design,
findings preview, contribution + roadmap; the roadmap paragraph closes the
section.
**Opens from:** cold open   **Hands to:** the data section assumes the reader
knows the 2003 rule change is the design.

- [ ] **Move 1 — Puzzle.** Open on the empirical regularity that independent-board
      firms earn higher post-buyback returns, and note that payout-preference
      stories predict no such gap. State the tension plainly.
- [ ] **Move 2 — Gap in prior work.** Prior studies measure payout levels, not
      timing, so they cannot separate the two explanations. `% CITE: prior work
      linking board independence to payout policy`
- [ ] **Move 3 — This paper.** Use the 2003 listing-rule shock to board
      composition as exogenous variation; describe the event-study design in one
      paragraph.
- [ ] **Move 4 — Findings preview.** Preview C1, C2, C4 with direction only
      (numbers go in Results). `% RESULT: headline CAR gap, fill from Table 3`
- [ ] **Move 5 — Contribution + roadmap.** The three contribution bullets, then a
      one-line section roadmap.
- [ ] **Draft** sections/intro.tex realizing Moves 1–5 in LaTeX.
- [ ] **Verify:** all five moves present; C1/C2/C4 stated; two slots marked; no
      invented numbers; hands cleanly to the data section.

### Section 4: Results  `sections/results.tex`  (~2,000 words, soft)

**Role:** Present the four tables in spine order; this is where numbers live.
**Realizes claims:** C1, C2, C3, C4
**Structure notes:** table-by-table walk in spine order; each table introduced
by the claim it tests, then the reading of its key estimate; footnotes minimal.
**Opens from:** methodology established the specification.  **Hands to:**
discussion interprets, does not re-report.

- [ ] **Move 1 — Buyback intensity (C1).** Walk Table 2; `\input{Tables/table_buyback_intensity.tex}`;
      state the sign and significance from the table, not from memory.
- [ ] **Move 2 — Return gap (C2).** Table 3 CARs by board type.
- [ ] **Move 3 — Asymmetry interaction (C3).** Table 4.
- [ ] **Move 4 — Design robustness (C4).** Table 5 IV/DiD; connect to the
      payout-preference alternative and why it fails here.
- [ ] **Draft** sections/results.tex realizing Moves 1–4, each anchored to its table.
- [ ] **Verify:** every table \input'd once; each claim's number read from its
      table; no result asserted without an anchor.
```

Sections 2, 3, 5, 6 follow the same block shape and are omitted here for brevity.
In a real plan, write every section block in full — the drafter may read them out
of order, so no block may lean on "same as Section 1".
