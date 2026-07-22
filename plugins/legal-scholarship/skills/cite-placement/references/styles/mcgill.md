# McGill Guide (9th ed.) — Citation Formatting Rules

Style-specific formatting for Phase 3b sub-agents. Structural rules
(anchors, grouping, status tracking) are in phase-details.md.

## Key Differences from Bluebook

- **supra note N** is in roman (not italicized) — unlike Bluebook's
  `\textit{supra}`.
- **Ibid** is italicized with NO period — `\textit{Ibid}` (not "Id.").
- **Et al** threshold is 4 (not 3), and written without a period.
- **Hereinafter** uses bracket notation: `[Author, \textit{Short Title}]`.
- **Abbreviations** omit periods in some cases ("no" not "no.", "ed" not "ed.").

## Citation Templates

**Journal articles:**
```latex
\footnote{See Author Name, \textit{Article Title} (Year) Volume:Issue
  \textsc{Journal Abbrev} First-Page (parenthetical).}
```
Example:
```latex
\footnote{See Jeffrey N Gordon, \textit{The Rise of Independent Directors in
  the United States, 1950--2005: Of Shareholder Value and Stock Market Prices}
  (2007) 59:6 \textsc{Stan L Rev} 1465 (tracing the rise of independent
  directors as the dominant governance institution).}
```

**Books:**
```latex
\footnote{See Author Name, \textit{Book Title} (Publisher, Year) at PAGE
  (parenthetical).}
```
Example:
```latex
\footnote{See Stéphane Rousseau \& Adriana Robertson, \textit{Public
  Enforcement of Securities Laws: Resource-Based Evidence} (Cambridge
  University Press, 2023) (examining enforcement patterns across
  jurisdictions).}
```

**Chapters in edited books:**
```latex
\footnote{See Author Name, \textit{Chapter Title} in Editor Name, ed,
  \textit{Book Title} (Publisher, Year) PAGE (parenthetical).}
```

**Working papers:**
```latex
\footnote{See Author Name, \textit{Title} (Working Paper, Year)
  (parenthetical).}
```

**Multi-citation footnotes** (semicolons between entries):
```latex
\footnote{See Author1, \textit{Title1} (Year1) Volume \textsc{Journal1} Page
  (parenthetical1); see also Author2, \textit{Title2} (Year2) Volume
  \textsc{Journal2} Page (parenthetical2).}
```

## Formatting Details

- **Author names**: Full first and last names. Regular case. Omit periods
  after initials ("Jeffrey N Gordon" not "Jeffrey N. Gordon").
- **Article titles**: `\textit{}` (italics).
- **Journal names**: `\textsc{}` (small caps) for this pipeline. Use
  standard abbreviations without periods ("L Rev" not "L. Rev.").
- **Book titles**: `\textit{}` (italics).
- **Year**: In parentheses before volume for journals: `(2007) 59`.
- **Volume:Issue** before journal name; **first page** after.
- **Pinpoint references**: Use "at" for books, comma for journals.
- **Escape special characters**: `&` → `\&` in LaTeX.
- **Footnotes end with a period.**

## Introductory Signals

| Signal | When to use |
|---|---|
| *See* | Direct support for the proposition |
| *See also* | Additional support |
| *Cf* | Support by analogy (no period, unlike Bluebook) |
| *But see* | Contrary authority |
| *See generally* | Background reference |
| *See e.g.* | One of several supporting sources |

## Journal Abbreviation Table (McGill style — minimal periods)

| Full Name | Abbreviation |
|---|---|
| McGill Law Journal | McGill LJ |
| University of Toronto Law Journal | UTLJ |
| Osgoode Hall Law Journal | Osgoode Hall LJ |
| Canadian Bar Review | Can Bar Rev |
| Queen's Law Journal | Queen's LJ |
| Supreme Court Law Review | SCLR |
| Stanford Law Review | Stan L Rev |
| Harvard Law Review | Harv L Rev |
| Yale Law Journal | Yale LJ |
| Journal of Financial Economics | J Fin Econ |
| American Economic Review | Am Econ Rev |
| Journal of Law and Economics | JL \& Econ |

For unlisted journals, abbreviate without periods (Journal → J,
Review → Rev, Economics → Econ, International → Intl, Law → L).

## Parentheticals

Same convention as Bluebook: present participle form ("finding...",
"establishing...", "arguing..."). Max ~15 words. Draw from screening
rationale or relationship field.

## Short-Form Conventions (reference only — handled by short_form.py)

- **Ibid**: `\textit{Ibid}` — italicized, NO period. Same source as
  immediately preceding footnote. Can appear in multi-citation footnotes.
- **supra note N**: Roman (not italicized), unlike Bluebook.
  `Author, supra note N`.
- **Hereinafter**: `[Author, \textit{Short Title}]` — bracket notation at
  first full citation when same author has multiple works.
- **Et al**: 4+ authors → `First-Author et al` (no period after "al").
