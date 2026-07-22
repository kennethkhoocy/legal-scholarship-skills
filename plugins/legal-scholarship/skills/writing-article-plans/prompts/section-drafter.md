# Section Drafter — Subagent Prompt

Use this to dispatch a fresh subagent that drafts ONE section of the article into
LaTeX from its plan block. Fill the bracketed slots and send as the task prompt.
Use Opus 4.8. Dispatch sections in spine order; run independent sections in
parallel, chain dependent ones.

```
You are drafting one section of an academic article from an approved plan.

Plan file: [ABSOLUTE PATH TO plan.md]
Section to draft: [Section N: Name] — write it to [sections/<name>.tex]
Structure notes: [the section block's Structure notes verbatim, or "none"]
Existing section source (revision mode): [path + section/¶ range of the source
material — for a .docx source draft this is the parsed-text artifact the plan
names, never the .docx itself — or "none — NEW section"]
Anchors you may reference (do not redraw): [paths/labels, or "none"]
Working directory: [project root]

## What to do
1. Read the plan file. Read the whole header (thesis, contribution, spine,
   claims register, terminology, evidence inventory) so your section is
   consistent with the rest of the paper, then read YOUR section block.
2. Write LaTeX prose that realizes each argument Move in the block, in order.
   Each move is roughly one paragraph. Write the actual argument the move
   states — you are executing a decided argument, not deciding one.
3. Reference tables and figures by \input or \ref to the given anchors. Never
   invent a table, a number, or a citation.

## Hard constraints
- Realize every Move. Do not add moves the plan does not list, and do not skip
  moves you find awkward — if a move seems wrong, draft it and flag the concern
  in a % comment; do not silently drop it.
- Numbers and results come only from the anchors or from the plan's stated
  results. Where the plan marks `% RESULT: …`, leave that exact comment in place
  for the author to fill; do not fabricate the number.
- Where the plan marks `% CITE: <kind>`, leave the slot in place at the point of
  use. Do not invent a citation key or a reference; the cite-placement pass fills
  the slot later. **Compile-safe footnote slot:** never write
  `\footnote{% CITE: ...}` on one line — the `%` comments out the rest of the
  line, including the closing `}`, leaving an unbalanced brace. Use the two-line
  form so it compiles to an (empty) footnote and stays greppable:

  ```latex
  \footnote{%
  % CITE: <kind of source>
  }
  ```

  A body-text (non-footnote) slot is just the bare comment line `% CITE: <kind>`
  after the sentence it supports. Which form to use follows the structure
  profile's citation architecture as carried in the Structure notes: body-text
  slots where the exemplar cites inline author-date (the empirical profile),
  footnote slots where citations live in footnotes (law_review, and
  footnote-citing theory exemplars).
- Use the terminology block's definitions verbatim; do not introduce synonyms
  for defined terms.
- Honor the section's "Opens from" / "Hands to" — open from the stated prior
  state and end where the next section can pick up.
- Honor the Structure notes: the section's internal organization, footnote
  policy, and any named formal environments are structural requirements, not
  style suggestions. Structure cannot be fixed downstream.
- Theory sections: write formal results in their statement environments
  (\begin{proposition}...\end{proposition}, lemma, assumption, theorem,
  definition) and proofs in \begin{proof}...\end{proof} — or in the appendix
  where the plan says so. Downstream tooling keys on these environments; a
  proposition written as a bold inline paragraph is a structural failure.
- Law-review sections: where a move marks content [substantive footnote: ...],
  write that content as real \footnote{...} prose. Citation-only support stays
  a two-line % CITE slot (form above). Do not promote footnote content into
  the body or demote body argument into footnotes.
- Revision mode (when an existing section source is given): text the plan marks
  as kept is copied byte-for-byte, never paraphrased. Existing citations
  (\cite keys, real footnotes) are carried through verbatim — never dropped,
  never converted to % CITE slots; slots are only for claims new to this
  revision. Existing numbers stay as written in the source. If a kept passage
  seems to conflict with a move, draft the move and flag the conflict in a
  % comment rather than rewriting the kept text.
- Output valid LaTeX for a section fragment (starts at \section{...}). Assume the
  preamble lives in main.tex. The word count is a soft target — keep to it
  roughly; never pad or truncate an argument to hit it. If the moves yield less
  prose than the target, deliver the shorter section: a restated claim or a
  filler paragraph is a defect a later pass must find and remove, which costs
  more than the words it added.
- Do not polish for voice or run any style pass — a later stage
  (style-emulation) restyles. Aim for correct, complete, plainly-written prose.
  In **standalone mode** (the orchestrator says so when style-emulation is not
  installed) there is no later restyle: this plain prose is the final prose, so
  keep it free of voice mimicry but make its clarity and polish
  delivery-quality rather than a rough draft awaiting a restyle.

## Return
Write the .tex file to the given path. Then report, in a few lines: which moves
you realized, any % RESULT / % CITE slots you left, any move you flagged as a
concern, and (revision mode) which source passages you kept verbatim versus
rewrote. Your reply is a status report to the orchestrator, not prose for the
paper.
```

## Reviewing a returned section

Before dispatching the next section, check the returned `.tex` against the plan
block's **Verify** step: every move present, named claims stated, slots preserved
(not fabricated), table/figure refs resolve, no invented numbers, Structure
notes honored (internal organization, footnote placement, formal environments),
and in revision mode: kept text verbatim, existing citations and numbers intact. If a check
fails, redispatch that section with the specific gap named rather than accepting a
partial draft.
