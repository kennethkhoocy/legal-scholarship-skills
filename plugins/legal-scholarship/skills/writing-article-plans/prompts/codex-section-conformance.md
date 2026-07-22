# Section Conformance Check — Codex Prompt (optional, per drafted section)

Independent cross-model version of the orchestrator's inline check in
`section-drafter.md` → "Reviewing a returned section". Dispatch after a
section-drafter subagent returns its `.tex`, when the section is long,
load-bearing, or the orchestrator's own context is saturated with the sections
it just reviewed. The plan is the ground truth; this is verification against an
artifact, not critique of the writing.

Dispatch: pipe the prompt below on stdin to `codex exec` with the session's
standard flags and `-o <scratch>/conformance_<section>.txt`. Sections are
independent — run several checks as parallel background jobs and read the
artifacts back. This check is single-shot: verify once, and on REDISPATCH re-send
the section to a fresh drafter with the named gaps (per `section-drafter.md`)
rather than looping the check itself to convergence.

```
You are checking a drafted LaTeX section against the plan block it was written
from. The plan is the ground truth: the drafter's contract was to realize the
plan's argument moves exactly — adding nothing, dropping nothing, inventing
nothing. Judge conformance only; do not evaluate prose quality or style (a
later pipeline stage restyles).

Plan file: [ABSOLUTE PATH TO plan.md]
Section block: [Section N: Name]
Drafted file: [ABSOLUTE PATH TO sections/<name>.tex]
Source draft (revision mode): [ABSOLUTE PATH to the source text the plan's
anchors use — the manuscript itself, or the parsed-text artifact for a .docx
source — or "n/a"]

Read the plan's header (thesis, spine, claims register, terminology, evidence
inventory) and the named section block, then the drafted .tex.

## Checks

| # | Check | Fail condition |
|---|-------|----------------|
| 1 | Moves realized | A move from the block has no corresponding passage, or appears out of order without cause. |
| 2 | No extra argument | The draft asserts a substantive claim, result, or argument move the block does not contain. (Connective prose and signposting are fine.) |
| 3 | Claim discipline | The section fails to state a claim from its "Realizes claims" list, or asserts another section's claim as already established contrary to "Opens from". |
| 4 | Slots preserved | A % CITE or % RESULT slot from the block is missing, altered, or filled with an invented citation key, reference, or number. Footnote slots must use the two-line brace-safe form (`\footnote{%` / `% CITE: …` / `}`). |
| 5 | No invented numbers | Any numeric result not traceable to a named anchor, the plan's stated results, or a % RESULT slot. |
| 6 | Anchor fidelity | \input/\ref targets outside the evidence inventory, a required anchor unused, or a table redrawn instead of referenced. |
| 7 | Terminology | A defined term replaced by a synonym or used contrary to its definition. |
| 8 | Handoff | The ending leaves the state the next section's "Opens from" expects; flagged-move % comments from the drafter are surfaced, not silently dropped. |
| 9 | Structure notes | The draft violates its block's Structure notes: internal organization ignored, [substantive footnote: …] content not in a real \footnote{...} (or body argument demoted into footnotes), a formal statement outside its environment, a proof not in \begin{proof} or the planned appendix. |
| 10 | Revision preservation (revision mode) | Text the block marks as kept is not verbatim in the draft; an existing citation from the Source material is dropped, altered, or turned into a % CITE slot; a number from the source changed. |

## Calibration

- Cite evidence for every failure: quote the offending line (or name the
  missing move) — no unanchored judgments.
- Wording differences between a move and its realization are fine; the test is
  whether the move's specific argument is made, not whether its phrasing recurs.
- Drafter % comments flagging a concern are compliant behavior — report them
  upward, do not count them as failures.
- A conforming section is CONFORMS. Do not pad the report.

## Output (exactly this shape)

VERDICT: CONFORMS | REDISPATCH

MOVES: [M1 ✓/✗, M2 ✓/✗, …]

FAILURES (if any):
- [check #, move/line]: [what is wrong] — [quoted evidence] → redispatch
  instruction: [the specific gap to name]

DRAFTER FLAGS: [any % comment concerns the drafter left, verbatim, or "none"]

SLOTS: [count of % CITE and % RESULT slots present vs. expected from the block]
```
