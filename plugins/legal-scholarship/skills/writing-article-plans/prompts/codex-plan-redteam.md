# Plan Red-Team — Codex Prompt (substantive gate)

Dispatch after the full plan is written, alongside or after the completeness
review (`plan-reviewer.md`), and **before** showing the plan to the user for
approval. Where `plan-reviewer.md` asks "can a drafter build from this?", this
pass asks "is the argument itself worth building?" — thesis, spine logic,
contribution claims, and the objections a hostile referee would raise. Run it
on Codex (GPT-5.5) so the critique comes from a different model family than the
one that wrote the plan.

**One round only.** The orchestrator fixes blocking findings in the plan, then
proceeds to user approval. Do not loop to convergence; a second red-team pass
runs only if the user asks for one after a major plan rewrite.

Dispatch: pipe the prompt below on stdin to `codex exec` with the session's
standard flags, `-o <scratch>/plan_redteam.txt`, and read the artifact back.
The plan file path must be absolute — Codex reads it itself. If the review
might benefit from web context, insert the standard Firecrawl grant per the
global CLAUDE.md at the marked slot; otherwise delete the slot line.

```
You are red-teaming an academic article plan before any prose is written. The
plan will be executed literally by drafter agents, so a flaw in the plan
becomes a flaw in the paper. Your job is substance only: attack the argument,
not the formatting. A separate reviewer has already checked completeness and
draftability — do not duplicate it.

Plan to review: [ABSOLUTE PATH TO plan.md]
Spec / author intent, for calibration: [SPEC PATH or one-paragraph summary]
[OPTIONAL FIRECRAWL GRANT — per global CLAUDE.md; delete this line if unused]

The plan's structure: a Thesis, Contribution bullets, an Argumentative spine of
claims C1…Cn (each with named evidence), a Claims register, a Terminology block,
an Evidence inventory, and per-section blocks of argument Moves that cite the
claim IDs they realize.

## Rubric — check each, in order

| # | Attack | What counts as a finding |
|---|--------|--------------------------|
| 1 | Thesis contestability | The thesis is a topic, a description, or a claim no reasonable scholar disputes — rather than a contestable position the paper must defend. |
| 2 | Spine logic | A claim Cn does not follow from, or is not independent of, the claims it builds on; support runs circular (Cn's evidence is Cm and vice versa); the weakest link would not survive a skeptical seminar. Name the single weakest inference in the spine even if it passes. |
| 3 | Contribution vs. evidence | A contribution bullet promises more than the evidence inventory can deliver — e.g., a causal or novelty claim resting on a % CITE slot, a descriptive table, or a result marked "not yet computed". |
| 4 | Unaddressed objections | State the two or three strongest objections a hostile referee would raise against the thesis (alternative explanations, scope limits, known counter-results you are aware of). For each, check whether any section move answers it. An objection no move addresses is a finding. |
| 5 | Evidence adequacy | For each spine claim, the evidence *type* is capable of supporting the claim *type* — a single cross-sectional table cannot carry a causal claim without a design; a literature slot cannot carry the paper's central empirical claim. |
| 6 | Cross-section contradiction | Two section blocks commit the paper to incompatible positions, or a late section quietly narrows/broadens the thesis. |

## Calibration

- Judge novelty and objections from your own knowledge of the field; the plan's
  own claims about prior work are assertions to test, not ground truth. Do not
  demand citations the plan already slots as % CITE — that is the later
  lit-review stage's job.
- Every finding must name its target (claim ID, section, move) and state the
  smallest change to the plan that would resolve it. An objection with no
  actionable fix is advisory, not blocking.
- Severity: **blocking** = a referee would reject or demand major revision on
  this ground; **advisory** = would strengthen the paper but its absence is
  survivable.
- A sound plan is a PASS. Do not manufacture findings to appear thorough; an
  empty blocking list with one or two sharp advisories is a good outcome.
- Out of scope: prose style, section lengths, formatting, completeness of the
  blocks, and anything the drafter or later pipeline stages (lit-review,
  cite-placement, and style-emulation when installed) will handle.
- Revision mode (the plan header says Mode: revision; the Source draft path is
  in the header): also test whether the plan resolves the weaknesses that
  motivated the revision — a restructure that reshuffles sections around an
  unfixed flaw is a finding. Judge KEEP decisions too: a kept section that
  contradicts the new spine is blocking.

## Output (exactly this shape)

VERDICT: PASS | REVISE

WEAKEST LINK: [the single most fragile inference in the spine, one sentence,
even on a PASS]

BLOCKING:
- [B1] [Claim/Section/Move]: [objection] → fix: [smallest plan change]
- …or "none"

ADVISORY:
- [A1] [target]: [objection] → [suggested strengthening]

REFEREE OBJECTIONS: [the 2–3 strongest, one line each, marked "answered by
Section N Move M" or "UNANSWERED"]
```
