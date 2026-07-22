---
name: expanding-shareholder-voice
genre: empirical
source: "Expanding Shareholder Voice: The Impact of SEC Guidance on Environmental and Social Proposals (law & finance empirical article)"
default: true
---

# Empirical structure — Expanding Shareholder Voice

Main text 12,753 words across 7 numbered sections; a separate Online Appendix of 10,562 words (≈83% of the main text) sits after the bibliography. 24 tables, 10 figures, all in back matter. 59 main-text footnotes.

## Section inventory and proportions
| # | Section | Role | ~Share of main-text words |
|---|---------|------|---------------------------|
| 1 | Introduction | Funnel: phenomenon → puzzle → question → results preview → roadmap | 16.0% |
| 2 | Contributions to the Literature | Standalone lit-review + contribution claim | 5.7% |
| 3 | Legal Framework and Data | Institutional/legal setting + data sources | 11.2% |
| 4 | Prescriptive Proposals and Shareholder Support | Measure construction + core proposal-level results | 26.1% |
| 5 | Prescriptive Proposals and Investor Characteristics | Fund-level results + subgroup heterogeneity | 24.7% |
| 6 | Political Backlash | Dedicated alternative-explanation rebuttal | 9.9% |
| 7 | Conclusion | Recap + interpretation + future work | 2.8% |
| — | Online Appendix (post-bibliography) | Full ML methodology, robustness, overflow tables/figures | ≈83% of main text (9 subsections) |

Two empirical results sections (4 and 5) carry ~51% of the main text; intro is large (16%); conclusion is deliberately short (~2.8%). The two heaviest sections escalate from proposal-level to fund-level analysis. (Shares are descriptive of this exemplar and need not sum to 100%; they are a soft guide to relative emphasis — per-article word targets are the planner's call, scaled to the article's own target length.)

## Heading and numbering conventions
- Standard `\section`/`\subsection`/`\subsubsection`; `secnumdepth=4` so `\paragraph` numbers as a 4th level, used only in the appendix.
- Titles are descriptive noun phrases, not argumentative sentences ("Fund Categories and Support for Prescriptive Proposals"); a few carry mild thesis flavor ("The Decline in Shareholder Support for E&S Proposals"). Sections 4 and 5 share a parallel "Prescriptive Proposals and X" title frame.
- Results sections go three levels deep (subsection = analytic step, subsubsection = one specification/subgroup); earlier sections stay two levels deep.

## Introduction architecture
17 paragraphs, 4 footnotes. Ordered moves:
- Move 1 — Phenomenon with concrete named examples (ExxonMobil, Meta, Lululemon) and the historical rise in support (~2 paras).
- Move 2 — Theories consistent with the rise, literature-anchored (~1 para).
- Move 3 — The reversal / puzzle: support fell 2022–23, with figures, pointing to Figure 1 (~1 para).
- Move 4 — Research question + the 2021 Guidance / ordinary-business-exclusion setup (~1 para).
- Move 5 — Define the key construct ("prescriptiveness") with an example (~1 para).
- Move 6 — Economic mechanism: the E&S-commitment vs pecuniary-cost trade-off (~1 para).
- Move 7 — Caveats and framework prediction (advisory nature; heterogeneity by preference intensity) (~2 paras).
- Move 8 — Prior mixed reactions to the Guidance (~1 para).
- Move 9 — Methods overview: supervised BERT + unsupervised topic modeling (~2 paras).
- Move 10 — Results preview, three findings in sequence (proposal-level, fund-level, ideological heterogeneity) (~3 paras).
- Move 11 — Interpretation ("walk the talk") and rebuttal of an alternative reading (~2 paras).
- Move 12 — Roadmap: final paragraph, enumerating every section by cross-reference.
Contribution: NOT a "we make three contributions" paragraph in the intro; the explicit contribution claim is deferred to Section 2. Roadmap: last intro paragraph.

## Per-section internal organization
- **Sec 2 (Contributions):** organized around "two distinct debates"; for each, states prior work → identifies the gap → asserts "our key contribution"; adjacent literature strands offloaded to footnotes.
- **Sec 3 (Framework & Data):** institutional/legal-setting subsection (rule, exclusion, no-action process, 2017→2021 policy shift, example table) THEN a data-sources subsection (source-by-source enumeration, merge procedure, sample-window justification).
- **Sec 4 & 5 (Results):** motivating-trend/summary-stats subsection first; then a measure/method subsection; then results subsections that each (i) state a numbered display-equation specification, (ii) define terms, (iii) "Table X presents our findings," (iv) walk columns naming fixed effects/subsamples, (v) report coefficients as economic magnitudes, (vi) note robustness across specs. Specifications escalate (baseline → add Post interaction → triple-DID). Threats to identification get their own subsubsections (selection effects; anti-ESG/new-proponents/new-targets).
- **Sec 6 (Political Backlash):** names one alternative hypothesis, then three subsections each rebutting it from a different angle (Big Three behavior, ESG fund flows, anti-ESG proposals); each states the hypothesis's prediction, runs a test, shows the predicted pattern is absent.
- **Sec 7 (Conclusion):** recaps phenomenon → headline findings with magnitude ranges → heterogeneity → robustness → broad interpretation → future-research list.

## Footnote architecture
Density ≈4.6 per 1,000 words (59 main text, 25 appendix), averaging ~32 words each — substantive, not terse. Zero pure citation-only footnotes: literature citations run inline in the body via natbib author-date (`\cite`, apalike). Footnotes carry cross-references to appendix sections and variable tables ("Further information ... in Table A1"; "see Section X"), methodological caveats (collinearity with year FEs, firm-vs-industry FE choice, log transforms), definitional clarifications (stop-words, terminology conventions), legal-source citations (C.F.R., case cites), and about a third mix a citation into substantive discussion.

## Signposting
- Roadmap is the final introduction paragraph, enumerating sections by `\ref`.
- Analytic subsections open with an infinitival purpose statement ("To examine how...", "To address concerns about...", "To establish...").
- Sections and subsections hand off with explicit backward and forward cross-references (`\ref` to prior sections and to appendix material); method detail is previewed conceptually in the body and pointed forward to the appendix.
- Each results block previews its specification (a numbered equation) before handing to a table.

## Idiosyncrasies (do not generalize)
- "Contributions to the Literature" as a standalone numbered Section 2 (framed as "two debates"), separate from the intro — a law-and-finance convention; "Article" is capitalized (law-review house style).
- Online Appendix ≈83% of main-text length, placed AFTER the bibliography, absorbing all ML methodology and overflow tables so the main text stays readable.
- All 24 tables and 10 figures collected in a back-matter float block after the bibliography, not embedded near their discussion.
- ML methods described twice (conceptual pass in body Sec 4.2; full technical documentation in the appendix).
- `secnumdepth=4` with numbered `\paragraph` as a 4th heading level — only in the appendix.
- One threat handled inline (selection effects, Sec 4) AND a whole section (Sec 6) devoted to a single alternative explanation.
- Every new regression specification gets its own numbered display equation before the table walk.
- Footnotes never used for bare citation despite the "Article"/law-review styling; that role belongs to inline author-date `\cite`.
