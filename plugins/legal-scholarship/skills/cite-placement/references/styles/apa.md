# APA (7th ed.) — Citation Formatting Rules (Footnote Adaptation)

Style-specific formatting for Phase 3b sub-agents. Structural rules
(anchors, grouping, status tracking) are in phase-details.md.

APA normally uses parenthetical in-text citations. This adaptation places
full APA-formatted references as footnote content, maintaining APA
conventions within `\footnote{}` commands.

## Key Differences from Legal Citation Styles

- **No introductory signals.** Do not use "See", "See also", "Cf.", etc.
- **Author names inverted**: Last, F. M. format (surname first, initials).
- **Article titles**: Sentence case, no italics, no quotes.
- **Journal names in italics** (`\textit{}`), title case.
- **Volume in italics**, issue in parentheses (not italicized).
- **DOI included** when available.
- **No ibid/supra convention.** Repeated citations use short author-date form.
- **Alphabetical order** within multi-citation footnotes.

## Citation Templates

**Journal articles:**
```latex
\footnote{Last, F. M., \& Last, F. M. (Year). Article title in sentence case.
  \textit{Journal Name in Title Case}, \textit{Volume}(Issue), Pages.
  https://doi.org/xxxxx}
```
Example:
```latex
\footnote{Gordon, J. N. (2007). The rise of independent directors in the
  United States, 1950--2005: Of shareholder value and stock market prices.
  \textit{Stanford Law Review}, \textit{59}(6), 1465--1568.}
```

**Books:**
```latex
\footnote{Last, F. M. (Year). \textit{Book title in sentence case}.
  Publisher Name. https://doi.org/xxxxx}
```
Example:
```latex
\footnote{Bebchuk, L. A., \& Fried, J. M. (2004). \textit{Pay without
  performance: The unfulfilled promise of executive compensation}.
  Harvard University Press.}
```

**Chapters in edited books:**
```latex
\footnote{Last, F. M. (Year). Chapter title in sentence case. In F. M. Last
  (Ed.), \textit{Book title} (pp. Pages). Publisher.}
```

**Working papers:**
```latex
\footnote{Last, F. M. (Year). \textit{Title in sentence case} (Working Paper
  No. XXX). Institution. https://doi.org/xxxxx}
```

**Multi-citation footnotes** (semicolons, alphabetical by first author):
```latex
\footnote{Bebchuk, L. A., \& Fried, J. M. (2004). \textit{Pay without
  performance}. Harvard University Press; Gordon, J. N. (2007). The rise
  of independent directors. \textit{Stanford Law Review}, \textit{59}(6),
  1465--1568.}
```

## Formatting Details

- **Author names**: Last, F. M. format. Use `\&` before last author.
  Single author: `Last, F. M.`
  Two authors: `Last, F. M., \& Last, F. M.`
  3--20 authors: list all, `\&` before last.
  21+ authors: first 19, `\ldots`, last author.
- **Article titles**: Sentence case (only first word, proper nouns, and
  first word after colon capitalized). No formatting.
- **Journal names**: `\textit{}`, title case. Use full journal names.
- **Book titles**: `\textit{}`, sentence case.
- **Volume**: `\textit{Volume}` (italicized). Issue in parentheses, not
  italicized: `\textit{59}(6)`.
- **Pages**: Use en-dash: `1465--1568`.
- **DOI**: Include when available, as URL: `https://doi.org/xxxxx`.
- **Year**: In parentheses immediately after author(s).
- **Escape special characters**: `&` → `\&`.
- **Footnotes end with a period.**

## Parentheticals

APA does not traditionally use Bluebook-style parentheticals. Instead, the
citation itself is the complete reference. If additional context is needed
for this pipeline, append a brief note after the citation:
`(examining the effect of board composition on firm value)`.

## Short-Form Conventions (reference only — handled by short_form.py)

- **No ibid.** APA does not use ibid.
- **No supra.** APA does not use supra note N.
- **Repeated citations**: Use short author-date form: `Author (Year)`.
- **No hereinafter.** Multiple works by the same author are distinguished
  by year (and letter suffixes if same year: 2007a, 2007b).
- **Et al.**: 3+ authors → `First-Author et al.`

## Pipeline Limitation

APA article titles are unformatted (no `\textit{}`), so the Phase 6 parser
identifies the journal name (the first `\textit{}` element) as the work
title for identity-key purposes. This does not affect output correctness
because APA repeats the same author-date short form regardless, but the
footnote registry may show journal names as "titles" for APA-formatted
citations. Inverted author names (`Last, F. M.`) may also affect author-key
extraction — Phase 3b sub-agents should use full first-last names in
footnotes even though APA reference lists invert names.
