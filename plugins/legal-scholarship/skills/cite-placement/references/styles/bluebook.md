# Bluebook (21st ed.) — Citation Formatting Rules

Style-specific formatting for Phase 3b sub-agents. Structural rules
(anchors, grouping, status tracking) are in phase-details.md.

## Citation Templates

**Journal articles:**
```latex
\footnote{See Author Name, \textit{Article Title}, VOLUME \textsc{Journal Abbrev.}\ PAGE (YEAR) (parenthetical).}
```
Example:
```latex
\footnote{See Jeffrey N. Gordon, \textit{The Rise of Independent Directors in
  the United States, 1950--2005: Of Shareholder Value and Stock Market Prices},
  59 \textsc{Stan.\ L.\ Rev.}\ 1465 (2007) (tracing the rise of independent
  directors as the dominant governance institution).}
```

**Books:**
```latex
\footnote{See \textsc{Author Name, Book Title} PAGE (YEAR) (parenthetical).}
```

**Working papers / SSRN:**
```latex
\footnote{See Author Name, \textit{Title} (Working Paper, YEAR) (parenthetical).}
```

**Unpublished manuscripts:**
```latex
\footnote{See Author Name, \textit{Title} (unpublished manuscript, YEAR) (parenthetical).}
```

**Multi-citation footnotes** (semicolons between entries):
```latex
\footnote{See Author1, \textit{Title1}, VOLUME \textsc{Journal1} PAGE (Year1)
  (parenthetical1); see also Author2, \textit{Title2}, VOLUME \textsc{Journal2}
  PAGE (Year2) (parenthetical2).}
```

## Formatting Details

- **Author names**: Regular case (not small caps) when following a signal. Full first and last names.
- **Article titles**: `\textit{}` (italics).
- **Journal names**: `\textsc{}` (small caps). Use standard Bluebook abbreviations.
- **Book titles**: `\textsc{}` (small caps), combined with author.
- **Volume number** before journal abbreviation; **page number** after.
- **Year** in parentheses at the end, before the parenthetical.
- **Escape special characters**: `&` → `\&` in LaTeX.
- **Footnotes end with a period.**
- If volume/page info is unavailable (working papers, SSRN), omit them.

## Introductory Signals

| Signal | When to use |
|---|---|
| *See* | Direct support for the proposition |
| *See also* | Additional support (not the primary source) |
| *Cf.* | Support by analogy — different context, same principle |
| *But see* | Contrary to the proposition |
| *See generally* | Background or foundational reference |
| *Compare ... with ...* | Two contrasting authorities |
| *E.g.,* | One of several sources supporting the point |
| *Accord* | Directly supports, from a different jurisdiction or context |

## Journal Abbreviation Table

| Full Name | Abbreviation |
|---|---|
| Yale Law Journal | Yale L.J. |
| Stanford Law Review | Stan. L. Rev. |
| Harvard Law Review | Harv. L. Rev. |
| Columbia Law Review | Colum. L. Rev. |
| Journal of Financial Economics | J. Fin. Econ. |
| Journal of Finance | J. Fin. |
| Review of Financial Studies | Rev. Fin. Stud. |
| American Economic Review | Am. Econ. Rev. |
| Quarterly Journal of Economics | Q.J. Econ. |
| Journal of Law and Economics | J.L. \& Econ. |
| Journal of Legal Studies | J. Legal Stud. |
| Journal of Law, Economics, and Organization | J.L. Econ. \& Org. |
| Journal of Corporate Finance | J. Corp. Fin. |
| Journal of Comparative Economics | J. Comp. Econ. |
| Journal of Management | J. Mgmt. |
| Strategic Management Journal | Strategic Mgmt. J. |
| Delaware Journal of Corporate Law | Del. J. Corp. L. |
| Yale Journal on Regulation | Yale J. on Reg. |
| Applied Economics | Applied Econ. |
| Frontiers in Psychology | Frontiers in Psych. |

For unlisted journals, apply standard Bluebook abbreviation rules
(Journal → J., Review → Rev., Economics → Econ., International → Int'l,
University → U., Law → L., American → Am.) or use the full name in small caps.

## Parentheticals

- One clause, present participle form: "finding...", "establishing...", "showing...", "arguing..."
- Draw from `screening_rationale` or `relationship` field.
- Max ~15 words.

## Short-Form Conventions (reference only — handled by short_form.py)

- **Id.**: `\textit{Id.}` — same source as immediately preceding footnote (sole citation only).
- **Supra**: `Author, \textit{supra} note N` — earlier footnote, different from immediately preceding.
- **Hereinafter**: `[hereinafter \textit{Short Title}]` — inserted at first full citation when same author has multiple works.
- **Et al.**: 3+ authors → `First-Author et al.`
