# An Inquiry into the Emulation Bot — Prompt & Interview Choices

> Companion record for `2026-07-01-emulation-bot-form-contribution-article-plan.md`.
> Captures the initial spec the skill was given and every interview question with
> its options and the option chosen. Reproduces the decisions the plan was built
> on so a reader can see *why* the plan is shaped the way it is.

**Skill:** writing-article-plans
**Article type:** law_review
**Plan produced:** `2026-07-01-emulation-bot-form-contribution-article-plan.md`

---

## Initial prompt (spec given to the skill)

Verbatim stream-of-consciousness outline the user supplied:

```
1.    Introduction
- broader topic: what AI can do to science and the academic profession
- specifically: language-based social sciences subject to soft criteria like
  language style and elegance; (1) student editors criteria? [to research]
  (2) publisher instructions of peer review in the law asks reviewers to consider
  form how arguments are presented
- distinction between "what to present" and "how to present"
- core question: is "presentation" [form] a feature of the academic output that is
  inseparable from the author, or is the "substance" what makes the academic
  contribution? What if we can isolate "form" from substance" using AI?
- Related technical question: Can AI adopt the style and elegance of the leading
  voices in the field? An Inquire into Emulation Bot
2.    Description of the Emulation Bot
a.    Functions
b.    Delineation
c.    Analogies
- AI-based movies remanufacturing features and movement of actors
- AI-based music modelling composition style of famous composers
o    AI-based art modelling artists' painting style
•    similarities and differences
•    Same underlying legal and ethical concerns personal form (language style) >
     substance (contribution to the field)
3.    Legal and Ethical Concerns
a.    Contract law
b.    Copyright Law
c.    Privacy Rights, as part of human dignity
d.    Data Protection
e.    Technology Law: AI Acts around the world
f.    Other [tbd]
4.    Policy Considerations
a.    Limiting Feeder Files to non-copyrighted works (expiry date)
b.    Consent Requirements for living authors
c.    Governance
d.    LINUX analogy => non-for profit, public domain tool for contributors that
     accept the LINUX open source conditions => written language = human code,
     similar to IT code in Linux
e.    [more]
5.    Conclusion
```

---

## Interview choices (option A/B/C/D per question)

Each question below is one round the skill asked before writing the plan.
`✅` marks the selected option; where the user typed a custom answer instead of
picking an enumerated option, it is recorded under **Answer (custom)**.

### Round 1 — Thesis

**Q:** What is the article's central thesis — the position you actually argue?
(Everything downstream hangs on this.)

- **A.** *Style is protectable authorship* — Form is inseparable from the author's
  persona; emulating a living scholar's voice without consent is a cognizable legal
  and dignitary wrong; the Linux-style consent/open-source regime is the fix.
- **B.** *Substance is the contribution* — Style is not protectable and emulation is
  largely permissible; the real, narrow risks are data protection and contract.
- **C.** *Form/substance separability* — The contribution is analytic: AI proves form
  and substance ARE separable, a gap current law does not address; legal/policy parts
  follow as implications without picking a strong pro/anti side.
- **D.** *Taxonomy + governance menu* — A framework paper taking no strong side; maps
  concerns across doctrines and offers a governance menu. Least committal.

**Answer (custom):** "Form is the contribution; this is a law review article
centered around the style-emulator skill." *(A committed pro-protection thesis in
the spirit of A, but grounded in the author's real style-emulation tool.)*

### Round 2 — The Bot description, and the normative payoff

**Q1 (The Bot):** Should Part 2 ("Description of the Emulation Bot") describe the
real style-emulation skill's architecture, or an abstracted bot?

- **A.** *Describe the real tool* — Anchor Part 2 to the actual pipeline
  (style-spec extraction, cross-model adversarial loop, paragraph-flow restyle, genres).
- **B.** *Abstracted emulation bot* — Described generically (inputs → style model →
  restyled output) so the legal analysis stays portable.
- **C.** *Hybrid: real as case study* — Abstract model for doctrine, real tool as a
  running worked example.

**Answer (custom):** "Abstraction in Part 2, but the details (option A) go in the
appendix." *(→ produced the split: abstracted body section + `appendix_architecture.tex`
anchored to the tool's real design docs.)*

**Q2 (Payoff):** Given "form is a contribution," what is the paper's normative
bottom line (drives Parts 3–4)?

- ✅ **A.** *Consent + attribution regime* — Emulating a living author's form requires
  consent and credit; the Linux-style open-source pool is the mechanism.
- **B.** *New protectable interest in style* — Argue for a quasi-IP / personality right
  in scholarly voice.
- **C.** *Recognize + light guardrails* — Recognize form-as-contribution but limit the
  fix to consent and data protection; no new IP.
- **D.** *Doctrinal menu, no single rule* — Present the Linux model as leading option
  without mandating one rule.

### Round 3 — Jurisdiction, venue/length, citation style

**Q1 (Jurisdiction):** Which legal system anchors the doctrinal analysis (Part 3)?

- ✅ **A.** *EU-anchored + comparative* — Lead with EU AI Act, GDPR, Continental
  moral-rights/dignity doctrine, with US contrast.
- **B.** *US-anchored + comparative* — Lead with US copyright/fair use, right of
  publicity, contract, US AI policy.
- **C.** *Broad comparative survey* — Roughly equal EU/US/UK/Asia; less depth each.
- **D.** *Principles-first, jurisdiction-light* — Each concern at the level of
  principle, jurisdictions only as illustrations.

**Q2 (Venue/length):** Target venue and length?

- **A.** *Full law review (~25k words)* — US long-form, heavy footnoting.
- ✅ **B.** *Intl. law journal (~12k words)* — European/international peer-reviewed
  length; tighter, argument-forward, still footnoted.
- **C.** *Essay (~8k words)* — Shorter conceptual essay; Part 3 selective.

**Q3 (Citations):** Footnote citation style?

- ✅ **A.** *OSCOLA* — UK/EU legal citation; fits an EU-anchored / international venue.
- **B.** *Bluebook* — US legal citation.
- **C.** *Chicago* — Author-date/notes; interdisciplinary venue.
- **D.** *Decide later* — Leave a citation-style slot in the header.

---

## How the choices shaped the plan

| Decision | Choice | Effect on the plan |
|----------|--------|--------------------|
| Thesis | Form **is** the contribution (pro-protection) | Spine C1–C6 built on separability → appropriation → consent regime |
| Bot description | Abstract in body, detail in appendix | Section 3 abstracted + `appendix_architecture.tex` anchored to real docs |
| Payoff | Consent + attribution regime | Section 5 (Governance) = feeder limits + consent + Linux open pool |
| Jurisdiction | EU-anchored + comparative | Section 4 leads EU (AI Act, GDPR, moral rights) with US contrast |
| Length | Intl. law journal (~12k) | Five doctrines merged into one Legal Concerns section (subsections) |
| Citations | OSCOLA | Header + every `% CITE:` slot targets OSCOLA footnotes |
