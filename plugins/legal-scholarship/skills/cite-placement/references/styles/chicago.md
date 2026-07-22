# Chicago Manual of Style (17th ed., notes-bib) — Citation Formatting Rules

Style-specific formatting for Phase 3b sub-agents. Structural rules
(anchors, grouping, status tracking) are in phase-details.md.

## Key Differences from Bluebook

- **No introductory signals.** Do not use "See", "See also", "Cf.", etc.
- **Journal names in italics** (`\textit{}`), not small caps.
- **Article titles in quotation marks** in print — use `\textit{}` in this
  LaTeX pipeline for consistency (avoids nested quotation mark issues).
- **Ibid.** (capitalized, with period) instead of Bluebook's `\textit{Id.}`.
- **Shortened title** for subsequent references (not "supra note N").
- **Publisher and place** included for books.

## Citation Templates

**Journal articles:**
```latex
\footnote{Author First Last, \textit{Article Title},
  \textit{Journal Name} Volume, no. Issue (Year): First-Page (parenthetical).}
```
Example:
```latex
\footnote{Jeffrey N. Gordon, \textit{The Rise of Independent Directors in the
  United States, 1950--2005: Of Shareholder Value and Stock Market Prices},
  \textit{Stanford Law Review} 59, no. 6 (2007): 1465 (tracing the rise of
  independent directors as the dominant governance institution).}
```

**Books:**
```latex
\footnote{Author First Last, \textit{Book Title} (Place: Publisher, Year),
  PAGE (parenthetical).}
```
Example:
```latex
\footnote{Lucian A. Bebchuk and Jesse M. Fried, \textit{Pay Without
  Performance: The Unfulfilled Promise of Executive Compensation}
  (Cambridge, MA: Harvard University Press, 2004) (arguing that executive
  compensation reflects managerial power rather than arm's-length bargaining).}
```

**Chapters in edited books:**
```latex
\footnote{Author First Last, \textit{Chapter Title}, in \textit{Book Title},
  ed. Editor First Last (Place: Publisher, Year), PAGE (parenthetical).}
```

**Working papers:**
```latex
\footnote{Author First Last, \textit{Title} (Working Paper, Institution, Year)
  (parenthetical).}
```

**Multi-citation footnotes** (semicolons between entries):
```latex
\footnote{Author1, \textit{Title1}, \textit{Journal1} Vol (Year): Page
  (parenthetical1); Author2, \textit{Title2} (Place: Publisher, Year)
  (parenthetical2).}
```

## Formatting Details

- **Author names**: First Last format. Full names. Regular case.
- **Article titles**: `\textit{}` (italics) in this pipeline.
- **Journal names**: `\textit{}` (italics). Use full journal names (Chicago
  does not mandate abbreviations, though common ones are acceptable).
- **Book titles**: `\textit{}` (italics).
- **Volume, issue**: `Volume, no. Issue (Year): Page`.
- **Publisher**: Include place and publisher for books.
- **Year**: In parentheses. For journals: after issue number. For books: at end.
- **Escape special characters**: `&` → `\&` in LaTeX.
- **Footnotes end with a period.**

## Parentheticals

Chicago does not traditionally use Bluebook-style parentheticals, but this
pipeline adds them for consistency. Use present participle form: "arguing...",
"finding...", "showing...". Max ~15 words. Draw from screening rationale.

## Short-Form Conventions (reference only — handled by short_form.py)

- **Ibid.**: Capitalized, with period. Same source as immediately preceding
  footnote. Sole citation only.
- **Shortened title**: `Author, \textit{Short Title}` — for subsequent
  references to a previously cited work. No "supra note N".
- **No hereinafter convention** in Chicago. Short titles are always used.
- **Et al.**: 4+ authors → "et al."
- **Two authors**: "Author1 and Author2" (not \&).
