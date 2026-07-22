---
name: liability-nondisclosure-ipos
genre: theory
source: "Liability for Non-Disclosure in IPOs (theory article)"
default: true
---

# Theory structure — Liability for Non-Disclosure in IPOs

Applied game-theory paper (law & economics; JLEO). Single model, solved once, then mined for normative and positive implications. Word counts are crude de-LaTeXed body words, excluding display math and footnote text; footnotes counted separately.

## Section inventory and proportions
| # | Section | Role | ~Share of main-text words |
|---|---------|------|---------------------------|
| 1 | Introduction | Motivating case, research questions, model preview, results preview, roadmap | 8% |
| 2 | Literature Review | Standalone related-work section placing paper vs. prior disclosure/IPO-litigation models | 5% |
| 3 | Legal Background | Domain (institutional/statutory) grounding — Section 11, class actions, reform proposals | 6% |
| 4 | The Model | Setup + preliminary analysis + equilibrium characterization + socially-optimal rule (4.1–4.3) | 40% |
| 5 | The Private Choice of Liability Rule | Extension: private design, private/social divergence, waivers (5.1–5.3) | 27% |
| 6 | Positive and Normative Implications | Empirical predictions + policy mapping (no new formal objects) | 8% |
| 7 | Conclusion | Recap + abstracted-away factors as future research | 5% |
| App A | Proofs | ALL proofs (9), ~37% of main-text length | — |
| App B | Supplemental Analyses | 4 extensions (credibility, stock sale, two-sided costs, entrepreneur liability), ~15% | — |

Analysis engine (Sec 4 + 5) is two-thirds of the main text. References are law-review style (full names, journal/vol/year), not author-date. An "Endnotes" block ([23]–[31]) trails App B — a pandoc artifact, not a real section.

## Heading and numbering conventions
Two real levels only: numbered sections (1–7) and numbered subsections (4.1–4.3, 5.1–5.3); no subsubsections. Titles are descriptive noun phrases, several argumentative ("The Socially-Optimal Liability Rule", "Divergence Between Private and Social Incentives"). Sections 4 and 5 are subdivided; 1–3, 6, 7 are flat.

## Introduction architecture
Seven paragraphs, no subsections:
1. Real-world case (Facebook IPO suit) as concrete hook.
2. Institutional framing → three explicit research questions (does liability induce disclosure / improve capital allocation / should firms design their own?).
3. Model preview, part 1: primitives and the adverse-selection problem (l-type withholds bad news → capital misallocation).
4. Model preview, part 2: liability mechanism + positive results (deterrence thresholds, comparative statics).
5. Normative result: socially-optimal rule is minimum-for-full-deterrence or zero.
6. Private-design result: private incentive to allow suits is socially excessive or insufficient (warranty intuition).
7. Explicit roadmap ("The paper is organized as follows…"), section by section; ends noting "All proofs are in Appendix A."

Contribution is woven through paras 3–6, not a standalone "we contribute X, Y, Z" paragraph. Related literature is deferred entirely to Section 2, not folded into the intro. Roadmap sits last.

## Formal-object conventions
Environments (pandoc-rendered as bold "Lemma 1." / "Proposition 1." / "Assumption 1:" paragraph openers), continuously numbered across the paper:
- Assumptions ×3 — all in Sec 4.1.
- Lemmas ×4 — Lemma 1, 2 (Sec 4.2), Lemma 3 (Sec 4.3), Lemma 4 (Sec 5 intro).
- Propositions ×4 — Prop 1 (4.2), Prop 2 (4.3), Prop 3 (5.1), Prop 4 (5.3).
- Corollaries ×2 — Cor 1 (5.2), Cor 2 (5.3).
- Proofs ×9 — every proof in Appendix A; none inline. Corollary 2 has no separate proof ("follows directly from Proposition 4").
- Figures ×3 (equilibrium regions; waiver divergence; entrepreneur-liability); no tables.
- Display equations numbered continuously to ~(40); main text references (1)–(18).

Ordering per result: setup prose → informal derivation/sketch of the threshold inline → **numbered statement** (often multi-case: Full / Partial / No Deterrence) → interpretation paragraph(s) unpacking each term. Proof placement is 100% appendix.

## Per-section internal organization
- **Sec 4 (Model).** Setup order: (i) primitives — E, capital c, personal cost e, cash flow x∈{x_h,x_l}, q, k≡c+e, x̄, and the ordering x_l<k<x̄<x_h; (ii) financing — equity fraction α, competitive investors, zero reservation; (iii) timing — 6 dated periods t=0..5 walked through one by one; (iv) information — hard-evidence/unraveling structure, types h/l/u, litigation signal σ, error rate λ; (v) payoffs/litigation — damages d, cost γd, lawyer rent (γ−γ₀)d, limited liability; (vi) welfare concept + equilibrium concept (PBNE) stated last. Then 4.1 benchmark (first-best) → moral-hazard assumptions.
- **Sec 4.2 (largest subsection, ~20% of main text).** Solve l-type participation β*, then investors' break-even α*, sketch each threshold, state Lemmas 1–2 and Proposition 1 (three regions), interpret, illustrate with Figure 1.
- **Sec 4.3 / 5.1 / 5.2 / 5.3.** Each opens by referring back to the prior result, extends the game or the objective, states one Lemma/Proposition/Corollary, then an intuition paragraph. 5.3 (largest in Sec 5) handles the general waiver with Prop 4 + Cor 2 + Figure 2.
- **Sec 6.** Three unnumbered thematic clusters of implications (IPO mis-pricing; deterrence correlates; private-ordering alignment), each tied back to a Proposition; prose only, no new statements.

## Footnote architecture
Very heavy: 55 footnotes over ~12,900 main-text words ≈ 4.2 per 1,000 words; footnote text ≈ 26% of body word count. Footnotes carry legal citations and case/statutory detail, robustness caveats and secondary modeling assumptions, extension pointers ("see Appendix B"), and empirical-evidence cites. Nearly all (54/55) sit in Sections 1–7; the proofs and supplemental analyses are almost footnote-free.

## Signposting
Roadmap explicit at end of Section 1. Sections open with a backward-linking transition ("The last section characterized…; we now explore…") and close by handing to the next. Results are consistently previewed in prose before being formally derived (sketch-then-Lemma). Figures are introduced after the corresponding proposition, as illustrations of an already-stated result.

## Idiosyncrasies (do not generalize)
- Section numbers are baked into heading TEXT ("4.2 Equilibrium Characterization") because pandoc suppressed real numbering — a plan should use genuine `\section` numbering, not literal digits in titles.
- Stray "Assumption 3:" and "Proof of Proposition 1." appear as their own subsection headings — pandoc mis-conversions of bold inline labels, not real subsections.
- A standalone **Literature Review** (Sec 2) and a **Legal Background** (Sec 3) *before* the model are field-specific (law & economics / JLEO); many pure-econ theory papers fold the literature into the intro and have no institutional section. Copy only if the target paper is similarly law-adjacent.
- Trailing "Endnotes" block and the law-review reference format are conversion/venue artifacts, not a model to imitate.
- Footnote density this high is characteristic of law & economics, not theory generally.
