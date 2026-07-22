# OSCOLA (4th ed.) — Citation Formatting Rules

Style-specific formatting for Phase 3b sub-agents. Structural rules
(anchors, grouping, status tracking) are in phase-details.md.

## Key Differences from Bluebook

- **No introductory signals.** Do not use "See", "See also", "Cf.", etc.
- **No period at end of footnotes.** OSCOLA footnotes end without punctuation.
- **Journal names in regular case** (not small caps in OSCOLA proper), but
  this pipeline uses `\textsc{}` for visual consistency across styles.
- **ibid** (roman, not italicized) for immediately preceding same source.
- **(n N)** cross-reference for earlier footnotes (not "supra note N").

## Citation Templates

**Journal articles:**
```latex
\footnote{Author Name, \textit{Article Title} (YEAR) VOLUME \textsc{Journal Abbrev} FIRST-PAGE}
```
Example:
```latex
\footnote{Jeffrey N Gordon, \textit{The Rise of Independent Directors in the
  United States, 1950--2005: Of Shareholder Value and Stock Market Prices}
  (2007) 59 \textsc{Stan L Rev} 1465}
```

**Books:**
```latex
\footnote{Author Name, \textit{Book Title} (Publisher YEAR)}
```
Example:
```latex
\footnote{Paul Davies and Sarah Worthington, \textit{Gower's Principles of
  Modern Company Law} (Sweet \& Maxwell 2016)}
```

**Chapters in edited books:**
```latex
\footnote{Author Name, \textit{Chapter Title} in Editor Name (ed),
  \textit{Book Title} (Publisher YEAR)}
```

**Working papers:**
```latex
\footnote{Author Name, \textit{Title} (Working Paper, YEAR)}
```

**Multi-citation footnotes** (semicolons between entries, no trailing period):
```latex
\footnote{Author1, \textit{Title1} (Year1) Volume \textsc{Journal1} Page;
  Author2, \textit{Title2} (Year2) Volume \textsc{Journal2} Page}
```

## Formatting Details

- **Author names**: Full first and last names. No inversion. Omit periods
  after initials (e.g., "Jeffrey N Gordon" not "Jeffrey N. Gordon").
- **Article titles**: `\textit{}` (italics).
- **Journal names**: `\textsc{}` for this pipeline. Use standard abbreviations
  (omit periods: "L Rev" not "L. Rev.").
- **Book titles**: `\textit{}` (italics).
- **Year**: In parentheses before volume for journals: `(2007) 59`.
- **Volume** before journal name; **first page** after (no "at" for pinpoints).
- **Pinpoint references**: Use comma: `1465, 1470` (not "at 1470").
- **No periods in abbreviations**: "edn" not "ed.", "vol" not "vol."
- **Escape special characters**: `&` → `\&` in LaTeX.
- **Footnotes do NOT end with a period.**

## Journal Abbreviation Table (OSCOLA style — no periods)

| Full Name | Abbreviation |
|---|---|
| Law Quarterly Review | LQR |
| Modern Law Review | MLR |
| Cambridge Law Journal | CLJ |
| Oxford Journal of Legal Studies | OJLS |
| Journal of Law and Society | JLS |
| European Law Review | EL Rev |
| Common Market Law Review | CML Rev |
| International and Comparative Law Quarterly | ICLQ |
| Stanford Law Review | Stan L Rev |
| Harvard Law Review | Harv L Rev |
| Yale Law Journal | Yale LJ |
| Journal of Financial Economics | J Fin Econ |
| Journal of Finance | J Fin |
| American Economic Review | Am Econ Rev |
| Journal of Law and Economics | JL \& Econ |

For unlisted journals, abbreviate without periods (Journal → J,
Review → Rev, Economics → Econ, International → Intl, Law → L).

## Parentheticals

OSCOLA uses explanatory parentheticals less frequently than Bluebook.
When used, keep them brief and descriptive — not required for every citation.
Place in parentheses after the citation: `(discussing the impact of...)`.

## Internal Cross-References

OSCOLA does not use "Infra" or "Supra" as cross-reference terms.
Convert to plain English:
- "Infra Part III" → "see Part III below"
- "Supra Part III" → "see Part III above"
- "Infra Part V, Section B" → "see Part V, Section B below"

No trailing period.

## Short-Form Conventions (reference only — handled by short_form.py)

- **ibid**: Roman (not italicized), no period. Same source as immediately
  preceding footnote. Can appear in multi-citation footnotes.
- **(n N)**: Cross-reference to footnote N. E.g., "Gordon (n 3)".
- **No hereinafter convention** in OSCOLA.
- **Et al.**: 4+ authors → "and others" (not "et al.").
