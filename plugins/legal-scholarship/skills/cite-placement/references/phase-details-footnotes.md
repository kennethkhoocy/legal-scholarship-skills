# Phase Details — Citation Placement as Footnotes

Detailed instructions for each phase of the **footnotes mode** of the
`cite-placement` skill (and, at the end, the independent **Restyle Pipeline**).
Read only the section relevant to the phase you are currently executing.

## Table of Contents

0. [Launcher](#launcher)
1. [Phase 1 — Manuscript Mapping](#phase-1--manuscript-mapping)
1.5. [Phase 1.5 — Existing Citation Audit](#phase-15--existing-citation-audit)
2. [Phase 2 — Citation Ingestion](#phase-2--citation-ingestion)
3. [Phase 3 — Placement Planning (Agentic Hybrid)](#phase-3--placement-planning-agentic-hybrid)
   - [Phase 3a — Assignment](#phase-3a--assignment)
   - [Phase 3b — Detailed Planning (per-section sub-agents)](#phase-3b--detailed-planning-per-section-sub-agents)
   - [Phase 3c — Consolidation](#phase-3c--consolidation)
4. [Phase 4 — HITL Review](#phase-4--hitl-review)
5. [Phase 5 — Execution](#phase-5--execution)

---

## Launcher

### Goal
Collect file paths from the user via a Tkinter GUI before running the pipeline.

### Steps

1. Run the launcher with a **10-minute timeout** (the user needs time to
   browse and configure):
   ```bash
   python "[skill-dir]/scripts/launcher.py"
   ```
   Use `timeout: 600000` when calling via the Bash tool. The `[skill-dir]` is
   the absolute path to the `cite-placement/` directory — use the skill's known
   location, not the current working directory.
2. The GUI presents fields for: Project Folder (optional), Input Manuscript
   (.tex or .docx), Input .xlsx, Output File, plus dropdowns for plan caching,
   HITL review, citation mode, and a verification checkbox. The user browses
   to select each file. Input and output format must match.
3. On the **Footnote Placement** run button, the launcher validates inputs,
   writes `placement/run_config.json` in the **output file's parent
   directory** (.tex or .docx), and prints the config to stdout. On cancel or window close,
   it prints `LAUNCHER_STATUS: cancelled`.
4. Parse the launcher's stdout to get the config path:
   - Look for `LAUNCHER_STATUS: success` — if missing or `cancelled`, stop.
   - Look for `LAUNCHER_CONFIG_PATH: <path>` — this is the absolute path to
     `run_config.json`. Use this path for all subsequent phases.
   - The config JSON is also printed to stdout for convenience.
5. Read `run_config.json` at the start of each subsequent phase to get paths:
   ```python
   import json
   from pathlib import Path
   config = json.loads(Path("<config_path>").read_text())
   # config["project_folder"]    — str or null
   # config["input_tex"]         — str (absolute path)
   # config["input_xlsx"]        — str (absolute path)
   # config["output_tex"]        — str (absolute path)
   # config["citation_style"]    — str ("bluebook", "oscola", "chicago", "apa", "mcgill")
   # config["pipeline"]          — str ("footnotes" or "restyle")
   # config["input_format"]      — str ("tex" or "docx")
   ```
   **Important**: All paths in `run_config.json` are absolute. Do not assume
   the config is in the current working directory — always use the absolute
   path from `LAUNCHER_CONFIG_PATH`.

6. **Pipeline routing**: Read `config["pipeline"]`:
   - `"footnotes"` → run the standard placement pipeline (Phases 1–6 below).
   - `"restyle"` → run the restyle pipeline (see **Restyle Pipeline** section
     at the end of this document). This is a separate flow that does not use
     the placement phases.

7. **Format routing**: Read `config["input_format"]`:
   - `"tex"` → standard LaTeX pipeline. Read/write `.tex` files with
     `\footnote{}` commands. Compile with xelatex.
   - `"docx"` → Word pipeline. Use `scripts/core/docx_support/` modules for
     reading manuscript content (extract_text.py), extracting existing
     footnotes (footnotes.py → extract_footnotes), and inserting new footnotes
     (footnotes.py → insert_footnote). The planning phases (1–3) use the
     Markdown extraction from extract_text.py instead of reading `.tex`
     directly. Phase 5 inserts OOXML footnotes instead of `\footnote{}`
     text. Phase 6 short-form processing operates on the extracted footnote
     text and writes back via replace_footnote_text. LaTeX formatting
     commands (`\textit{}`, `\textsc{}`) are converted to Word run
     properties (italic, small caps) via converter.py.

   **Important**: When `input_format` is `"docx"`, skip all LaTeX-specific
   steps: no xelatex compilation, no `%CITE-PLACED` markers, no
   `\bibliography{}` removal. The `.docx` format uses its own footnote
   numbering via OOXML.

---

## Phase 1 — Manuscript Mapping

### Goal
Build a detailed paragraph-level map of the manuscript to guide citation placement.

### Cache Check

Before doing any work, read `replan` from `run_config.json`:
- If `replan` is `false` and `placement/section_map.md` exists → skip this
  phase. Print "Using cached section map." If the input `.tex` file is newer than
  `section_map.md`, also print: "Note: manuscript has been modified since the
  section map was generated. Using cached version. Select 'Force regenerate' to
  rebuild."
- If `replan` is `true` → regenerate regardless.

### Steps

1. Read the entire `.tex` manuscript.
2. Create directory `placement/` in the project directory if it doesn't exist.
3. Produce `placement/section_map.md` with the following structure:

```markdown
# Manuscript Map: [Manuscript Title]

## Section 1 — [Section Title]

### Subsection 1.1 — [Subsection Title]

#### Paragraph 1 (starting with "[first ~8 words]...")
- **Argument/claim**: [What this paragraph argues or establishes]
- **Mechanisms/variables**: [Key concepts, variables, or theories invoked]
- **Existing citations**:
  - Footnote 3: "See Author, Title (Year) (parenthetical)" — supports [Y]
- **Existing footnotes without citations**:
  - Footnote 2: "[content]" — [purpose]

#### Paragraph 2 (starting with "[first ~8 words]...")
...
```

### What to Record

For every paragraph:
- The **specific claim or argument** — not just "discusses X" but "argues that
  mandatory disclosure increases firm value through reduced information asymmetry."
- **All mechanisms, variables, and concepts** invoked (e.g., "information
  asymmetry", "bid-ask spread", "voluntary disclosure").
- **Every existing `\footnote{}`** with: its number (if determinable), its full
  content, what authors/works it cites, what claim it supports, and its
  **type classification** (see below).
- **Equations and formal results**: Note them briefly — citations near formal
  results often support the derivation methodology or assumptions.

### Footnote Classification

Classify every existing footnote into one of these types:

| Type | Description | Verify? |
|---|---|---|
| `article` | Journal article citation | Yes |
| `book` | Book or book chapter citation | Yes |
| `working_paper` | Working paper, SSRN, NBER | Yes |
| `case` | Case citation | No |
| `legislation` | Statute, regulation, guidance | No |
| `cross_reference` | Supra, infra, internal reference | No |
| `discursive` | Author commentary, data notes | No |
| `mixed` | Contains multiple types | Verify citation portions only |

Include the type in `section_map.md` alongside each footnote:
```markdown
- **Existing citations**:
  - Footnote 3 [article]: "See Gordon, *Title*, 59 STAN. L. REV. 1465 (2007)" — supports [Y]
- **Existing footnotes without citations**:
  - Footnote 5 [cross_reference]: "Infra Section II.A"
  - Footnote 7 [discursive]: "The median figure is computed from..."
```

For `mixed` footnotes, identify the citation portions separately from
cross-references or discursive text.

### Structured Extraction: `existing_footnotes.json`

In addition to `section_map.md`, produce
`placement/existing_footnotes.json` — a structured extraction of all
footnotes classified as `article`, `book`, `working_paper`, or the citation
portions of `mixed` footnotes. For each, extract:

```json
[
  {
    "footnote_number": 3,
    "type": "article",
    "raw_text": "See Jeffrey N. Gordon, \\textit{The Rise of Independent Directors...}, 59 STAN. L. REV. 1465 (2007).",
    "extracted_author": "Jeffrey N. Gordon",
    "extracted_title": "The Rise of Independent Directors in the United States, 1950-2005",
    "extracted_year": 2007,
    "extracted_journal": "Stanford Law Review"
  }
]
```

The `extracted_*` fields are parsed from the footnote text by the LLM during
mapping. They provide structured input for the Phase 1.5 verification script.

This extraction always runs regardless of the `verify_citations` flag — it is
lightweight (part of the mapping pass) and useful for Phase 3 context even
without verification.

### Citation Slots (`% CITE:`)

Drafts produced by the `writing-article-plans` skill mark intended citation
sites with typed placeholder slots — `% CITE:` LaTeX comments carrying a hint
(e.g. `% CITE: meta-analysis on Y`, `% CITE: study establishing X`). A slot is
an author-declared demand for a citation, distinct from any citation already in
a manuscript footnote. Slots are a `.tex` convention only — when `input_format`
is `"docx"` there are no slots, so skip this subsection and all slot handling in
Phases 3a, 3b, 4, and 5.

While mapping a `.tex` manuscript, enumerate **every** `% CITE:` slot. Three
forms occur:

- **`bare`** — `% CITE: <hint>` on its own line or at the end of a line.
- **`footnote_two_line`** — the brace-safe post-assembly form:
  ```latex
  \footnote{%
  % CITE: <hint>
  }
  ```
- **`footnote_one_line`** — `\footnote{% CITE: <hint>}`. Compile-unsafe: the `%`
  comments out the closing brace. When any slot of this form appears, recommend
  the user first run `writing-article-plans`' `assemble_manuscript.py`, which
  normalizes slots into the brace-safe two-line form.

Record every slot under a new top-level `citation_slots` array. Because the
extraction now carries slots as well as footnotes, write
`existing_footnotes.json` as an object wrapping both arrays:

```json
{
  "footnotes": [ "...the footnote-citation entries shown above..." ],
  "citation_slots": [
    {
      "slot_id": "S1",
      "section": "II",
      "anchor": "% CITE: meta-analysis on Y",
      "hint": "meta-analysis on Y",
      "form": "footnote_two_line"
    }
  ]
}
```

The `anchor` is the exact `% CITE:` comment line, verbatim — for a footnote-wrapped
slot it is the inner `% CITE: <hint>` line, never the surrounding `\footnote{…}`
shell. The `form` field records whether that line sits inside a footnote shell, so
Phase 5 can locate the slot deterministically and know how to fill it.
Slots do **not** count as existing footnotes — they are demands to be filled, not
citations already present, and never appear in the `footnotes` array. Report the
slot count in the Phase 1 console summary (e.g. "Found 7 `% CITE:` slots (3 bare,
4 footnote-wrapped)"). Leave `% RESULT:` comments untouched — they belong to a
different pipeline.

**Phase 1.5 compatibility.** `verify_citations.py` accepts both forms — the
legacy bare array and the object form with `footnotes`/`citation_slots` keys —
so pass `existing_footnotes.json` to the verifier directly in either case.

### Why This Matters

Phase 3 uses this map to decide where each new citation belongs. A vague map
("this section discusses corporate governance") leads to vague placements. A
precise map ("Paragraph 3 argues that board independence reduces tunneling,
citing Shleifer & Vishny 1997 for the theoretical mechanism") lets Phase 3
place a new tunneling citation with confidence.

### Constraints
- **Read-only**: Do not modify the `.tex` file or any other source file.
- Record the map accurately — do not invent content that isn't in the manuscript.
- If the manuscript has no section structure (flat document), use paragraph
  numbering as the organizing unit.

---

## Phase 1.5 — Existing Citation Audit

### Goal
Verify existing academic citations in the manuscript against external APIs.
Detect hallucinated citations, check Bluebook formatting, and flag overlaps
with the incoming RA spreadsheet. Produces `audit_report.json` consumed by
Phases 3a and 5.

### Gate Check

Read `verify_citations` from `run_config.json`:
- If `false` (default): skip this phase entirely. Print "Citation verification
  disabled — skipping Phase 1.5." Phase 1 still classifies footnote types and
  produces `existing_footnotes.json` (this is lightweight, part of the mapping
  pass), but no API verification runs.
- If `true`: proceed with the full verification cascade.

### Steps

1. Read `placement/existing_footnotes.json` (produced by Phase 1). Both file
   forms (bare array, or object with `footnotes`/`citation_slots` keys when
   slots are present) are accepted by the verifier directly.
2. Run the verification script:
   ```bash
   python "[skill-dir]/scripts/core/verify_citations.py" \
     --mode footnotes \
     --footnotes "[output-dir]/existing_footnotes.json" \
     --output "[output-dir]/audit_report.json" \
     --spreadsheet "[config.input_xlsx]"
   ```
3. Review console output. If hallucinated citations are flagged, print them
   prominently. If unverified citations need manual review, list them.

### Verification Cascade

For each academic citation (`article`, `book`, `working_paper`), the script
tries in order:

1. **OpenAlex** — free, no key. Title search with Jaccard word-set matching.
2. **CrossRef** — free, no key. Fallback if OpenAlex misses.
3. **Google Scholar via SearchAPI** — optional, requires `SEARCHAPI_API_KEY`
   env var. Catches Chinese-language papers and recent working papers.

A citation is **verified** if title Jaccard > 0.85, year matches (±1), and at
least one author last name matches. It is **hallucinated** if all APIs return
results but best Jaccard < 0.5. Otherwise it is **unverified** (ambiguous).

### Output: `placement/audit_report.json`

Contains per-citation verification status, format issues, corrected Bluebook
strings, and spreadsheet overlap flags. See `scripts/core/verify_citations.py`
for the full schema.

### How Downstream Phases Use the Audit

**Phase 3a**: If `audit_report.json` exists, read it. Hallucinated citations
do not count as "already cited" — if the RA spreadsheet has a real paper for
that location, assign it normally. Overlapping citations (verified + in
spreadsheet) are noted as "reformat with RA version" rather than skipped.
If `audit_report.json` does not exist, treat all existing citations as valid.

**Phase 5**: If `audit_report.json` exists, apply fixes to the output `.tex`:
- **Hallucinated**: remove the footnote. Print warning.
- **Format issues**: replace with `corrected_bluebook` string.
- **Overlaps**: replace with the RA-formatted version from Phase 3b.
- **Verified, no issues**: leave untouched.
- **Unverified**: leave untouched, print warning for manual review.
If `audit_report.json` does not exist, skip all audit fixes.

---

## Phase 2 — Citation Ingestion

### Goal
Convert the `.xlsx` citation spreadsheet into structured JSON and BibTeX format.

### Steps

1. Read `run_config.json` to get `input_xlsx` and determine the output directory
   (parent of `output_tex`).
2. Scan the output directory (and `project_folder` if set) for any existing `.bib`
   file. If found, use it for `--existing-bib`.
3. Run the ingestion script:
   ```bash
   python "[skill-dir]/scripts/core/ingest_citations.py" \
     --input "[config.input_xlsx]" \
     --output-json "[output-dir]/citations.json" \
     --output-bib "[output-dir]/references_new.bib" \
     --existing-bib "[path-to-existing-bib]"
   ```
   Omit `--existing-bib` if no existing .bib file was found.
   Optional: `--min-score N` skips spreadsheet rows whose `screening_score` is below N (default 0 = no filtering).
4. Review the console summary (N ingested, N duplicates, N written).
5. If any issues are reported (e.g., missing required fields), inform the user.

### Column Mapping

The script auto-detects columns. Expected defaults:

| Excel Column | JSON Field | BibTeX Field | Notes |
|---|---|---|---|
| `title` | `title` | `title` | Required |
| `authors` | `authors` | `author` | "A and B and C" in BibTeX |
| `year` | `year` | `year` | Required |
| `journal` | `journal` | `journal` | Blank → `@unpublished` |
| `DOI` | `doi` | `doi` | Optional |
| `abstract` | `abstract` | — | JSON only |
| Relevance col | `relevance_note` | — | Auto-detected; JSON only |
| `relationship` | `relationship` | — | JSON only |
| `screening_rationale` | `screening_rationale` | — | JSON only |
| `screening_score` | `screening_score` | — | JSON only |
| `paper_type` | `paper_type` | — | JSON only |
| `identification_strategy` | `identification_strategy` | — | JSON only |
| `source` | `source` | — | JSON only |

Relevance column detection priority:
1. Exact match: `Relevance`
2. Any column containing "relevance" (case-insensitive), e.g., `(JP) Relevance`

Unrecognized columns are passed through to JSON as-is.

### Cite Key Format

Google Scholar style: `lastnameYEARfirstword`
- `lastnameYEARfirstword` → e.g., `mackinlay1997event`
- Multi-author: use first author's last name only
- Collision: append `b`, `c`, etc.
- Last name extraction: use the first author, take the surname, lowercase, strip
  accents/diacritics

### Duplicate Detection

When `--existing-bib` is provided:
1. Match on DOI only (exact, case-insensitive, URL prefixes stripped)
2. If no DOI on either side, no match is attempted — the citation passes through
3. Duplicates are flagged `"already_in_bib": true` in JSON
4. Duplicates are excluded from `.bib` output but retained in JSON for Phase 3
   awareness

---

## Phase 3 — Placement Planning (Agentic Hybrid)

### Goal
Determine exactly where each new citation should be placed, draft the **full
Bluebook-formatted footnote text**, and record a **verbatim anchor string**
for deterministic insertion. No `\cite{}` commands.

Phase 3 is split into three sub-phases to solve an output volume problem: a
single LLM pass drops citations when the batch is large (~80–120). The fix
separates cross-sectional judgment (short output, works in single context)
from detailed placement writing (long output, parallelized across sub-agents).

### Cache Check and Incremental Mode

Read `replan` from `run_config.json`:

**When `replan` is `true` (full regenerate):**
- Delete the existing `placement_plan.md`, `assignment.json`, and
  `section_plans/` directory if present.
- Run Phase 3a → 3b → 3c from scratch for all citations in `citations.json`.
- Write a fresh plan with all entries as Status `new`.

**When `replan` is `false` (cached / incremental):**
1. If `placement_plan.md` does not exist → run from scratch (same as
   `replan: true`).
2. If `placement_plan.md` exists:
   a. Read the `planned_keys` header (HTML comment at top of the file).
   b. Load `citations.json` from Phase 2.
   c. Diff: find cite keys in `citations.json` that are **not** in `planned_keys`.
   d. If no new citations → skip all of Phase 3. Print: "No new citations to
      plan. Using cached plan ([N] existing placements)."
   e. If new citations exist → Phase 3a produces an assignment for **only the
      new citations**. Phase 3b spawns agents only for sections that have new
      assignments (each agent also receives the existing plan entries for its
      section to avoid conflicts). Phase 3c appends new placements to the
      existing `placement_plan.md` under a dated header. Updates `planned_keys`.
   f. If the input `.tex` is newer than the plan, print: "Note: manuscript has
      been modified since the plan was generated. Using cached version. Select
      'Force regenerate' to rebuild."

### `planned_keys` Header

The first line of `placement_plan.md` must be an HTML comment listing all cite
keys that have placements in the plan:

```
<!-- planned_keys: gordon2006rise, adams2010role, gilson2001globalizing -->
```

This line is machine-readable. Phase 3a reads it to determine which citations
are new. When appending incremental placements, update this line to include the
new keys. When generating from scratch, write all keys.

---

### Phase 3a — Assignment

#### Goal
Produce a lightweight assignment mapping — which citations go where — in a
single LLM pass. Citations can be assigned to **multiple sections**. The same
source routinely appears 2–5 times across a law review article (e.g., framing
the argument in the Introduction, then returning to it in the institutional
analysis). Phase 6 converts repeat occurrences to `\textit{supra}` note N —
Phase 3a's job is to identify every location where a citation belongs.

Phase 3a operates in one of two modes, controlled by `citation_mode` in
`run_config.json`:
- **`selective`** (default): Selectivity applies **per-placement**. Each
  placement must attach to a specific claim. Weak placements are dropped but
  strong placements in multiple sections are kept.
- **`comprehensive`**: Place at every relevant location regardless of
  placement strength. The only valid skip reason is `already_cited`.

#### Input
- `placement/section_map.md`
- `placement/citations.json`
- The `.tex` manuscript
- `citation_mode` from `run_config.json`

#### Slot Pass (mandatory — runs before ordinary assignment)

If `existing_footnotes.json` carries a non-empty `citation_slots` array, a
mandatory slot pass runs **before** the ordinary assignment steps. Each slot is
an author-declared citation demand and must be resolved; it is exempt from
selective culling.

For each slot in `citation_slots`:

1. Read the typed `hint` together with the slot's surrounding text (its `anchor`
   and the paragraph in `section_map.md`).
2. Match the hint against `citations.json`, reading the `title`, `abstract`,
   `relationship`, `relevance_note`, and `screening_rationale` fields:
   - Assign **one or more** `cite_key`s that satisfy the hint. A hint naming a
     class of sources (e.g. "meta-analyses on Y") may take 2–3 keys.
   - If the hint names an explicit cite key that already exists in
     `citations.json` or the existing `.bib`, use that key as-is.
3. If no key in `citations.json` (or the existing `.bib`) satisfies the hint,
   record the slot in the `unfilled_slots` array with a concrete `reason`
   (e.g. "no meta-analysis on Y in spreadsheet").

Every slot ends the pass either assigned one or more cite keys (in
`slot_assignments`) or listed in `unfilled_slots`. `citation_mode` does not
apply to slots — `selective` governs only free placements and never skips a
slot. The full formatted footnote text for each filled slot is written by the
slot's Phase 3b section sub-agent.

#### Steps

1. Load all inputs into a single context. Read `citation_mode` from
   `run_config.json` (default to `"selective"` if the key is absent).
2. For each citation in `citations.json` (excluding `already_in_bib: true`
   unless the citation appears uncited in the manuscript):
   - Use `relevance_note`, `relationship`, `screening_rationale`, and `abstract`
     to understand what the citation contributes.
   - **Scan every section** in `section_map.md` for paragraphs where the same
     argument, mechanism, or variable is discussed. Do not stop after finding
     the first match — actively look for multiple placement opportunities.
   - For each matching location, record the target paragraph, a Bluebook
     signal, a brief reason, and a `placement_strength` (`"strong"` or
     `"weak"`).
3. Cross-reference against existing `\footnote{}` content in `section_map.md`.
   If an author/title already appears in a manuscript footnote, place the
   citation in the `skipped` list with reason `"already_cited"`.
   **Audit override**: If `audit_report.json` exists, check the audit status
   of each existing citation before treating it as "already cited":
   - **Hallucinated** existing citations do NOT count as already cited.
     Assign the RA citation normally — Phase 5 will remove the hallucinated
     footnote.
   - **Overlaps with spreadsheet** — note as "reformat with RA version"
     rather than skipping. The RA spreadsheet metadata takes priority for
     formatting.
   If `audit_report.json` does not exist, treat all existing citations as
   valid (current behavior).

#### Assignment Rules

1. **Identify ALL placement locations.** For each citation, check every
   section — not just the most obvious one. A foundational work like Gordon
   (2006) might support a claim in the Introduction, appear again in the
   empirical discussion, and be referenced a third time in the institutional
   analysis.

2. **Assign placement strength to each placement:**
   - `"strong"` — the citation directly supports, contrasts with, or extends a
     specific sentence or claim at this location.
   - `"weak"` — the citation is relevant to the general topic of the paragraph
     but does not attach to a specific assertion.

3. **Expected multi-placement rate:** In a typical law review article, 30–50%
   of citations should have 2+ placements. If fewer than 20% have multiple
   placements, re-examine whether the pass is being too conservative.

#### Citation Mode: Selective (default)

Selectivity applies **per-placement**, not per-citation:

1. **Keep only strong placements.** Drop any placement with
   `placement_strength: "weak"`. A citation with 3 placements might keep 2
   (strong) and drop 1 (weak).

2. **Every kept placement must attach to a specific claim.** Topical relevance
   to the paper's general subject area is not sufficient at any location.

3. **Methodological references need a specific anchor** at each location where
   they appear.

4. **At each location, if multiple citations support the same claim, keep the
   strongest 1–2.** Note the preferred cite key in the skip reason:
   `"duplicative of [preferred_key] at [section_id]"`.

5. **Do not cull aggressively.** Law review articles are heavily footnoted —
   200–400 footnotes is normal. When in doubt, keep the placement.

6. **A citation is only fully skipped** (no placements at all) if it has zero
   strong placements anywhere in the manuscript. Skip with reason
   `"no_specific_claim"`.

#### Citation Mode: Comprehensive

Place at every relevant location regardless of placement strength. Both
`"strong"` and `"weak"` placements are kept. The only valid skip reason is
`"already_cited"`.

#### Skip Reasons Reference

| Reason | Applies in | Meaning |
|---|---|---|
| `already_cited` | Both modes | Author/title already appears in a manuscript footnote |
| `no_specific_claim` | Selective only | Zero strong placements anywhere in the manuscript |
| `methodological_no_anchor` | Selective only | Methods/reference work with no procedural claim at any location |
| `duplicative of [key] at [section]` | Selective only | Another citation makes the same point more authoritatively at this location |

#### Output: `placement/assignment.json`

The schema is **citation-centric** — each citation has a `placements` array
listing every location where it should appear:

```json
{
  "citations": [
    {
      "cite_key": "gordon2006rise",
      "placements": [
        {
          "section_id": "I",
          "target_paragraphs": ["paragraph starting with 'Corporate boards have a fixed...'"],
          "signal": "See",
          "brief_reason": "canonical reference on rise of independent directors",
          "placement_strength": "strong"
        },
        {
          "section_id": "III.B.2",
          "target_paragraphs": ["paragraph starting with 'The formal categories that governance...'"],
          "signal": "See",
          "brief_reason": "returns to independence argument in institutional context",
          "placement_strength": "strong"
        }
      ]
    },
    {
      "cite_key": "gilson2001globalizing",
      "placements": [
        {
          "section_id": "I",
          "target_paragraphs": ["paragraph starting with 'These comparisons matter at scale...'"],
          "signal": "See",
          "brief_reason": "convergence of governance reforms across jurisdictions",
          "placement_strength": "strong"
        }
      ]
    }
  ],
  "slot_assignments": [
    {
      "slot_id": "S1",
      "section": "II",
      "anchor": "% CITE: meta-analysis on Y",
      "form": "footnote_two_line",
      "hint": "meta-analysis on Y",
      "cite_keys": ["smith2020meta", "jones2019review"]
    }
  ],
  "unfilled_slots": [
    {
      "slot_id": "S4",
      "section": "III",
      "anchor": "% CITE: study establishing X in emerging markets",
      "form": "bare",
      "hint": "study establishing X in emerging markets",
      "reason": "no matching source in citations.json or references.bib"
    }
  ],
  "skipped": [
    {
      "cite_key": "somekey2024",
      "reason": "already_cited in Section I, Paragraph 2"
    },
    {
      "cite_key": "anotherkey2023",
      "reason": "no_specific_claim"
    }
  ],
  "stats": {
    "total_citations": 113,
    "citations_with_placements": 92,
    "total_placements": 148,
    "multi_placement_citations": 38,
    "multi_placement_rate": 0.41,
    "skipped": 21,
    "citation_mode": "selective"
  }
}
```

To feed Phase 3b, the pipeline converts this citation-centric format into a
per-section view: for each section, collect all placements targeting that
section along with their citation metadata.

#### Validation

After generating `assignment.json`, verify completeness (both modes):
- Every citation in `citations.json` must appear in either `citations` (with
  at least one placement) or in `skipped`.
- Print a count to console: "Assigned [N] citations ([P] total placements,
  [M] multi-placement) across [S] sections. Skipped [K] (mode:
  [selective/comprehensive]). Total: [N+K]/[total]."
- If the numbers don't sum to the total, flag it as an error and list the
  missing cite keys.
- If `multi_placement_rate` < 0.20, print a warning: "Low multi-placement
  rate ([rate]). Consider whether the assignment pass is too conservative."
- Every slot in `citation_slots` must appear in either `slot_assignments` or
  `unfilled_slots`. Print a slot line: "Slots: [N] found, [M] filled, [K]
  unfilled."

#### Bluebook Signal Reference

| Signal | When to use |
|---|---|
| *See* | Direct support for the proposition |
| *See also* | Additional support (not the primary source) |
| *Cf.* | Support by analogy — different context, same principle |
| *But see* | Contrary to the proposition |
| *See generally* | Background or foundational reference |
| *Compare ... with ...* | Two contrasting authorities |

---

### Phase 3b — Detailed Planning (per-section sub-agents)

#### Goal
For each section with assigned citations, spawn a sub-agent that writes the
full placement entries (anchors, Bluebook footnotes, justifications). Each
sub-agent handles ~20–40 citations — a comfortable generation volume. Sub-agents
run in parallel.

#### Input per sub-agent
1. The full `section_map.md` (for global awareness of paper structure).
2. The **full text** of its assigned section from the `.tex` file (extracted by
   line range).
3. The full metadata (from `citations.json`) for every citation that has **any
   placement** in this section — not just citations whose primary section is
   this one. A citation placed in Sections I and III.B.2 sends its metadata to
   both sub-agents.
4. The placement entries for this section from `assignment.json` (target
   paragraphs, signals, brief reasons).
5. A list of all existing `\footnote{}` commands in its section (from
   `section_map.md`) for duplicate avoidance.
6. In incremental mode: the existing plan entries for its section, so it can
   avoid conflict with already-placed citations.
7. Any `slot_assignments` entries whose `section` is this section, each with its
   `slot_id`, `anchor`, `hint`, slot `form`, and assigned `cite_keys`.

**Important:** The sub-agent does not need to know whether a citation appears
in other sections. Every placement gets the **full citation string** in the
selected style. Phase 6 handles short-form conversion for repeat occurrences.

#### Slot Placements (listed first)

If the section has `slot_assignments` entries (from Phase 3a), the sub-agent
lists them **first** in its output, before any free placement, each as a
placement entry with placement type `slot`:

- **Type**: `slot`
- **Slot form**: `bare` | `footnote_two_line` | `footnote_one_line`
- **Anchor**: the exact slot text to locate. For a `bare` slot, the
  `% CITE: <hint>` comment (extend with the preceding sentence if needed to make
  it unique). For a footnote-wrapped slot, the `% CITE: <hint>` comment line
  inside the braces.
- **Replace slot with**: the complete formatted footnote text in the run's
  citation style (the citation body that goes inside `\footnote{}`), built from
  the slot's assigned `cite_keys` and joined with semicolons for multiple keys.
  Phase 5 wraps it per the slot form: a new `\footnote{%CITE-PLACED …}` for a
  bare slot, or filled in place after `%CITE-PLACED` inside the existing shell
  for a footnote-wrapped slot.
- **Status**: new
- **Cite keys**: the assigned keys.

Slots listed in `unfilled_slots` are **not** placed; they are carried to the
Phase 4 report and left untouched in the manuscript.

Example (`.tex`):
```markdown
### Slot S1 (hint: "meta-analysis on Y")
- **Type**: slot
- **Slot form**: footnote_two_line
- **Anchor**: "% CITE: meta-analysis on Y"
- **Replace slot with**: See Author A, \textit{Title A}, 12 \textsc{Journal} 1 (2020); Author B, \textit{Title B}, 8 \textsc{Journal} 44 (2019).
- **Status**: new
- **Cite keys**: smith2020meta, jones2019review
```

#### Loading Style-Specific Formatting Rules

Before constructing the sub-agent prompt, read `citation_style` from
`run_config.json` (default: `"bluebook"`). Then read the formatting rules
from `references/styles/<citation_style>.md` in the skill directory. This
content replaces the hardcoded Bluebook rules in the prompt template below.

#### Sub-Agent Prompt Template

Use the following template to construct each sub-agent's prompt. Fill in the
`[VARIABLES]` from the pipeline data. Replace `[STYLE_FORMATTING_RULES]`
with the content of the style `.md` file.

```
You are placing citations as formatted footnotes in one section of an
academic article.

## Your section
Section [SECTION_ID]: [SECTION_TITLE]
Lines [START]–[END] of the manuscript.

## Full paper structure (for context only — do not place citations outside your section)
[SECTION_MAP_CONTENT]

## Section text
[SECTION_TEX_CONTENT]

## Citations to place
[CITATION_METADATA_JSON — only entries assigned to this section]

## Assignment guidance from Phase 3a
[ASSIGNMENT_ENTRIES_FOR_THIS_SECTION — target_paragraphs, signal, brief_reason for each]

## Existing footnotes in this section
[EXISTING_FOOTNOTES_LIST — from section_map.md]

## Existing plan entries for this section (incremental mode only)
[EXISTING_PLAN_ENTRIES — if any, so agent avoids conflicts; omit if full regenerate]

## Instructions
For each assigned citation, produce a placement entry with:
- Anchor (verbatim unique substring from the section text)
- Full formatted footnote text (per the citation style rules below)
- Justification (1-2 sentences)
- Status: new
- Cite key

### Citation formatting rules

[STYLE_FORMATTING_RULES — insert the full content of references/styles/<citation_style>.md here]

### Anchor rules
- Copy the anchor EXACTLY from the .tex, including LaTeX commands and line breaks.
- The anchor must be UNIQUE within the .tex file. Use the last sentence or clause.
  If too short, extend with more preceding text.
- The anchor must NOT include an existing \footnote{} at its end.
- For append-to-footnote entries, the anchor identifies the text before the existing \footnote{.

### Grouping
- If 2+ citations target the same paragraph and support the same claim, combine
  into one multi-citation footnote (semicolons between entries).
- If they support different claims, place at distinct sentence-level locations.

## Output format
Write your output as markdown with this structure:

## Section [SECTION_ID] — [SECTION_TITLE]

### Paragraph N (starting with "[first ~8 words]...")
- **Anchor**: "exact verbatim text from .tex ending at insertion point."
- **Insert after anchor**: \footnote{See Author, \textit{Title}, ...}
- **Justification**: [1-2 sentences]
- **Status**: new
- **Cite key**: gordon2006rise

[For append-to-footnote entries:]
### Paragraph N (starting with "[first ~8 words]...")
- **Append to footnote after anchor**: "text before existing footnote."
- **Append text**: ; see also Author, \textit{Title}, ...
- **Justification**: [1-2 sentences]
- **Status**: new
- **Cite key**: smith2020example

Every assigned citation must appear in your output. Print a count at the end:
"Section [ID]: [N] placements for [M] assigned citations."
```

#### Output: `placement/section_plans/section_[ID].md`

Each sub-agent writes its output to a separate file. The file follows the same
placement entry format as the final `placement_plan.md`.

#### Spawning

Use the Claude Code `Agent` tool with `subagent_type: "general-purpose"` for
each section. Spawn all section agents in a single message for parallel
execution. Name each agent `cite-3b-section-[ID]` so progress can be tracked.

---

### Phase 3c — Consolidation

#### Goal
Merge all per-section plans into a single `placement_plan.md`, validate
completeness, and handle any cross-section issues.

#### Input
- All section plan files from `placement/section_plans/`.
- `assignment.json` (for the skipped list and stats).

#### Steps

1. Read all section plan files.
2. Order sections by manuscript sequence.
3. **Keep all placements.** Do NOT deduplicate across sections. If a cite key
   appears in Section I and Section III.B.2, both placements appear in the
   final plan. Phase 6 converts the second occurrence to `\textit{supra}`.
4. **Merge same-anchor placements into single footnotes.** After collecting all
   placements, scan for entries that share the **same anchor string** (or
   whose anchors resolve to the same insertion point — i.e., identical anchor
   text, or overlapping anchors that would produce adjacent `\footnote{}`
   commands at the same sentence boundary). When duplicates are found:

   a. **Combine** the footnote texts into a single `\footnote{}` body, joined
      by semicolons. Strip the trailing period from all constituent citations
      except the last.
   b. **Signal word casing**: The first citation keeps its capitalized signal
      word (e.g., `See`). All subsequent citations' signal words become
      lowercase (e.g., `see also`, `cf.`). Signals to handle (case-insensitive):
      `See`, `See also`, `Cf.`, `But see`, `But cf.`, `See generally`,
      `Compare`, `E.g.`, `Accord`.
   c. **Ordering**: Sort merged citations by `placement_strength` (strong
      before weak), then by spreadsheet row order as tiebreaker.
   d. **Cite keys**: The merged entry's `**Cite key**` line lists all
      constituent cite keys comma-separated. The `planned_keys` header still
      lists each key once.
   e. **Justification**: Combine justifications from all constituent entries,
      separated by " | ".
   f. Print: "Merged [N] placements at anchor '[first 50 chars]...' into
      single footnote ([cite_key1], [cite_key2], ...)."

   Example merged entry in `placement_plan.md`:
   ```markdown
   ### Paragraph 5 (starting with "The independent director market...")
   - **Anchor**: "pendent director market."
   - **Insert after anchor**: \footnote{See Daniel Berkowitz, Chen Lin \& Sibo Liu, \textit{De-politicization and Corporate Transformation: Evidence from China}, \textsc{J.L. Econ.\ \& Org.} (2021) (documenting effects of depoliticization on corporate transformation); see also Jyun-Ying Fu \& Pei Sun, \textit{Closing the Revolving Door}, \textsc{J.\ Mgmt.} (2023) (documenting long-term consequences of closing the revolving door).}
   - **Justification**: Direct support for independent director market claim | Additional evidence on revolving door effects
   - **Status**: new
   - **Cite key**: berkowitz2021depoliticization, fu2023closing
   ```

5. Write the `planned_keys` HTML comment header at the top. List each cite key
   **once** (it tracks which citations have been planned, not how many
   placements each has).
6. Append the `## Skipped Citations` section from `assignment.json`.
7. Write the consolidated output to `placement/placement_plan.md`.
8. Print summary: "Consolidated [P] placements ([N] unique citations) across
   [M] sections from [K] sub-agents. Merged [G] groups of same-anchor
   placements. Skipped [S] citations."

#### Validation

Every citation in `citations.json` must appear in either the plan (with at
least one placement) or in the skipped list. If any citation is missing,
flag it as an error and list the missing cite keys.

#### Output: `placement/placement_plan.md`

Same format as before — compatible with Phase 4 and Phase 5:

```markdown
<!-- planned_keys: gordon2006rise, gilson2001globalizing, hermalin1995endogenously -->
# Placement Plan

## Section I — [Section Title]

### Paragraph 3 (starting with "[first ~8 words]...")
- **Anchor**: "the organizing principle of governance reform from Delaware to\nShenzhen."
- **Insert after anchor**: \footnote{See Ronald J. Gilson, \textit{Globalizing Corporate Governance: Convergence of Form or Function}, 49 \textsc{Am.\ J.\ Comp.\ L.}\ 329 (2001) (analyzing whether corporate governance reforms converge across jurisdictions).}
- **Justification**: [1-2 sentences]
- **Status**: new
- **Cite key**: gilson2001globalizing

### Paragraph 5 (starting with "[first ~8 words]...")
- **Append to footnote after anchor**: "the controller's management\nstyle."
- **Append text**: ; see also Author, \textit{Title}, VOLUME \textsc{Journal} PAGE (YEAR) (parenthetical)
- **Justification**: [1-2 sentences]
- **Status**: new
- **Cite key**: author2020example

---

## Section II — [Section Title]

...

---

## Skipped Citations

- `jones2023` — already cited in Section 2, Paragraph 1
```

For incremental additions, append under a dated header:
```markdown

---
## Incremental additions — 2026-03-22

### Paragraph 2 (starting with "[first ~8 words]...")
- **Anchor**: "advisory contract cannot replicate."
- **Insert after anchor**: \footnote{...}
- **Justification**: ...
- **Status**: new
- **Cite key**: newauthor2025example
```

#### Incremental Consolidation

In incremental mode, Phase 3c reads the existing `placement_plan.md` and
appends only the new section entries under a dated header. It updates the
`planned_keys` line to include the new keys. Existing entries are untouched.

---

### Shared Reference: Citation Formatting Rules

Citation formatting rules are now in style-specific files under
`references/styles/<citation_style>.md`. The sub-agent prompt template
above includes a `[STYLE_FORMATTING_RULES]` placeholder — replace it
with the content of the appropriate style file based on `citation_style`
from `run_config.json`.

Available styles: `bluebook`, `oscola`, `chicago`, `apa`, `mcgill`.

For Phase 3a (signal selection), also check the style .md file — some
styles (OSCOLA, Chicago, APA) do not use introductory signals at all.

### Anchor Rules

Each placement must include a **verbatim anchor string** — an exact substring
of the `.tex` file that uniquely identifies the insertion point. Phase 5 uses
this for deterministic find-and-insert when working from a cached plan.

- Copy the anchor **exactly** from the `.tex`, including LaTeX commands. If the
  text spans multiple lines in the `.tex`, include the newline as `\n` in the
  anchor or reproduce the exact whitespace.
- The anchor must be **unique** within the `.tex` file. Typically the last
  sentence or clause of the paragraph/sentence. If too short or common, extend
  it with more preceding text.
- The anchor must **not** include an existing `\footnote{}` at its end. Stop
  before any existing footnote.
- For append-to-footnote entries, the anchor identifies the text *before* the
  existing `\footnote{` so that Phase 5 can find the right footnote to modify.

### Status Tracking

- `new` — not yet inserted. Phase 5 processes this entry.
- `inserted` — already inserted in a prior run. Phase 5 skips this entry.

After Phase 5 inserts a footnote, it updates that entry from `new` to
`inserted` in the plan file.

### Constraints
- **Read-only**: Do not modify any source files during Phase 3.
- Use the manuscript text itself (not just the map) to find precise sentence
  boundaries for placement and to construct accurate anchors.

---

## Phase 4 — HITL Review

### Goal
Get user approval before modifying any files — unless auto-approve is enabled.

### Steps

1. Read `auto_approve` from `run_config.json`.

2. **Always** print the placement plan to console (summary table or full plan).
   When the manuscript contained `% CITE:` slots, **lead** the summary with a
   headline slot line before the ordinary placement summary:
   ```
   Slots: N found, M filled, K unfilled
   ```
   List every unfilled slot (`slot_id`, `hint`, `reason`) immediately under this
   line. Unfilled slots are the headline item — the user sees them before the
   ordinary placement summary.

3. **If `auto_approve` is `false`** (default):
   - Tell the user:
     > "I've created the placement plan at `placement/placement_plan.md`.
     > Please review it and let me know:
     > - Any placements to **remove** (citation doesn't belong there)
     > - Any placements to **move** (right citation, wrong location)
     > - Any placements to **reword** (change signal, parenthetical, or formatting)
     > - Any **additional citations** you want placed that I missed
     > - Any changes to the **order** within multi-cite footnotes
     > - Any **unfilled `% CITE:` slots** to resolve (point me at the right
     >   source, or confirm leaving the gap)
     >
     > When you're satisfied, tell me to proceed with Phase 5."
   - Wait for the user's response. Do not proceed until explicitly told to.
   - If the user requests changes, update the plan and wait for confirmation.

4. **If `auto_approve` is `true`**:
   - Print: "Auto-approve enabled — proceeding to Phase 5."
   - Continue immediately to Phase 5 without pausing.

### Why This Checkpoint Exists

Citation placement is a scholarly judgment call. The LLM can get the mechanics
right (formatting, signals, deduplication) but the author knows which citations
truly strengthen their argument at each point. Auto-approve is for iterative
runs where the plan has already been reviewed and only formatting or new-batch
insertions are happening.

---

## Phase 5 — Execution

### Goal
Insert the planned footnotes into a new copy of the manuscript and compile.

### Step 1 — Create Output File

1. **Copy the manuscript** to the output path specified in `run_config.json`.
   - Default: `{name}_cited.tex` (e.g., `Manuscript.tex` → `Manuscript_cited.tex`)
   - If the output file already exists: overwrite it (it's a derived file).
   - **Never modify the original `.tex`.**

2. **Remove any `\bibliography{}` or `\bibliographystyle{}` commands** from the
   output file if present.

### Step 1.5 — Apply Audit Fixes (if audit_report.json exists)

If `placement/audit_report.json` exists, read it and apply fixes to the
output `.tex` before inserting new footnotes:

1. **Hallucinated citations**: For each citation with `"status": "hallucinated"`,
   find and remove the corresponding `\footnote{...}` from the output file.
   Print: "Removed hallucinated citation at footnote [N]: [title]".
2. **Format issues**: For each citation with `"format_issues"` and a
   `"corrected_bluebook"` string, replace the footnote text with the corrected
   version. Print: "Reformatted footnote [N]: [issue summary]".
3. **Spreadsheet overlaps**: For citations flagged `"overlaps_with_spreadsheet":
   true`, the footnote text will be replaced by the Phase 3b sub-agent's
   output during insertion (the RA spreadsheet version takes priority).
4. **Unverified citations**: Leave untouched. Print: "Unverified citation at
   footnote [N] — manual review recommended."

If `audit_report.json` does not exist, skip this step entirely.

### Step 1.7 — Fill Citation Slots

If Phase 3a produced `slot_assignments`, fill each assigned slot in the output
`.tex` before free-placement insertion. The replacement text comes from the
`Type: slot` entries in `placement_plan.md` (the Phase 3b/3c output); the
`slot_assignments` array in `assignment.json` carries only the key assignment
(slot → cite keys), not the formatted footnote text. Fill by exact string
replacement, using each slot entry's `**Anchor**` to locate the slot. The
mechanic depends on the slot `form`:

**Bare slot** (`form: bare`): replace the `% CITE: <hint>` comment with a new
`\footnote{%CITE-PLACED\n<formatted citation>}` attached to the anchor sentence
per the normal insertion rules. The `% CITE:` comment must not survive.
```latex
% Before:  ...reduces information asymmetry. % CITE: meta-analysis on Y
% After:   ...reduces information asymmetry.\footnote{%CITE-PLACED
See Author A, \textit{Title A}, ...; Author B, \textit{Title B}, ...}
```

**Footnote-wrapped slot** (`form: footnote_two_line` or `footnote_one_line`):
fill **in place** — replace the `% CITE: <hint>` comment line inside the braces
with `%CITE-PLACED` followed by the formatted citation text, preserving the
existing `\footnote{…}` shell. For the one-line form, rewrite to the brace-safe
multi-line result.
```latex
% Before:  ...shape financial development.\footnote{%
%          % CITE: study establishing X
%          }
% After:   ...shape financial development.\footnote{%CITE-PLACED
See La Porta et al., \textit{Law and Finance}, ...}
```

**Unfilled slots** (listed in `unfilled_slots`): leave untouched — the
`% CITE:` comment stays in the manuscript to keep flagging the gap. If a slot's
anchor is not found, print a warning and treat it as unfilled.

**Never** modify `% RESULT:` comments or any other comment; only `% CITE:`
slots that have a `slot_assignments` entry are touched. When `input_format` is
`"docx"`, there are no slots — skip this step.

### Step 2 — Insert Footnotes (Two Modes)

Read `replan` from `run_config.json` to determine the insertion mode.

#### Mode A: Deterministic insertion (`replan: false` — cached plan)

This mode uses exact anchor matching. No LLM judgment for placement.

1. Read `placement/placement_plan.md`. Parse each entry.
2. **Skip** all entries with `**Status**: inserted`.
3. For each entry with `**Status**: new`:

   **For "Insert after anchor" entries:**
   a. Find the **Anchor** string in the `.tex` using exact string matching.
   b. If found: insert the footnote text immediately after the anchor.
   c. If not found: print "Anchor not found — skipping: [first 50 chars]..."
      and skip. Do NOT attempt fuzzy matching or LLM interpretation.

   **For "Append to footnote after anchor" entries:**
   a. Find the anchor string in the `.tex`.
   b. Locate the `\footnote{` that immediately follows the anchor.
   c. Find the matching closing `}` (counting brace depth).
   d. Insert the append text before the closing `}`.

4. After each successful insertion, update that entry's `**Status**` from
   `new` to `inserted` in `placement_plan.md`.

#### Mode B: LLM-guided insertion (`replan: true` — fresh plan)

This mode uses the LLM's understanding of the manuscript. The anchors are
present in the plan (Phase 3 always generates them) but the LLM may use its
judgment if the anchor text doesn't match exactly (e.g., minor manuscript edits
since the plan was generated).

1. Read the placement plan. All entries are `new`.
2. For each entry, find the insertion point using the anchor as a guide.
   If the exact anchor is not found, use the surrounding context (section,
   paragraph description, justification) to locate the correct position.
3. Insert the footnote.
4. Update status to `inserted` after each successful insertion.

### Step 2.4 — Tag Pre-Existing Footnotes

After all insertions and audit fixes, tag any pre-existing `\footnote{}` that
does not already contain `%CITE-PLACED`. Use the same logic as
`scripts/migrate_markers.py`: find every `\footnote{` with a brace-depth
parser, check if content starts with `%CITE-PLACED`, and if not, insert
`%CITE-PLACED\n` after the opening brace. This ensures every footnote in the
output `.tex` is marked, enabling `strip_citations.py` to remove all of them.

### Step 2.5 — Merge Adjacent Footnotes (safety net)

After all insertions are complete (and after Step 1.5 audit fixes), run the
merge script as a defensive post-processing pass. This catches any adjacent
`\footnote{...}\footnote{...}` patterns that slipped through — from cached
plans, incremental additions, or audit-fix insertions.

```bash
python "[skill-dir]/scripts/merge_adjacent_footnotes.py" \
  --input "[config.output_tex]" \
  --output "[config.output_tex]" \
  --style "[config.citation_style]" \
  --skill-dir "[skill-dir]"
```

The script loads the style JSON config for separator, signal lowercasing,
and end-punctuation rules. It:
1. Scans for adjacent `\footnote{...}\footnote{...}` separated only by
   whitespace/newlines. Uses a brace-depth counter (not naive regex) to
   correctly handle nested braces in footnote content.
2. Merges adjacent footnotes into one: strips trailing punctuation from all
   but the last, joins with the style's separator, lowercases signal words
   after the first (if the style uses signals).
3. Logs each merge (footnotes combined, line number) for audit.

This step runs **before** Phase 6 (short_form.py) because short-form
processing depends on final footnote numbering. If no adjacent footnotes are
found, the script prints "No adjacent footnotes found" and returns cleanly.

### Step 2.6 — Slot Closure Check (deterministic)

If the input manuscript contained `% CITE:` slots, verify slot closure on the
output `.tex` after all slot filling and footnote insertion:

```bash
grep -n "% CITE:" "[config.output_tex]"
```

Reconcile the grep hits against `unfilled_slots` deterministically: each
`grep -n "% CITE:"` hit must match the `anchor` of exactly one `unfilled_slots`
entry. A hit matching no `unfilled_slots` entry is a forgotten slot — go back and
fill it (or, if genuinely unfillable, add it to `unfilled_slots` and report it).
An `unfilled_slots` entry with no surviving grep hit is a slot that was actually
filled but misreported — correct the report so the counts agree. When every hit
maps one-to-one to a distinct `unfilled_slots` entry (and every entry to a hit),
the run is consistent; otherwise reconcile and re-run the check before reporting
done. `% RESULT:` and other comments are expected to remain and are ignored by
this check, which matches only `% CITE:`. This step is `.tex` only; `.docx` runs
have no slots.

Include the reconciliation line in the final run report:
```
Slots: N found, M filled, K unfilled; grep remaining % CITE: = K (matches unfilled).
```

### Step 3 — Compile and Report

1. After all insertions, compile:
   ```
   xelatex [file]
   ```
   One pass is sufficient — footnotes are self-contained text.
   **No `bibtex` or `biber` pass.**
2. Check for errors. If compilation fails:
   - Identify the problematic footnote(s) from the log.
   - Fix the issue (usually an unescaped `&`, unmatched brace, or bad
     `\textsc{}`/`\textit{}` nesting).
   - Re-compile to confirm.
3. Report the final state:
   - Number of footnotes inserted (status changed from `new` to `inserted`)
   - Number of entries skipped (already `inserted`)
   - Number of anchors not found (skipped in Mode A)
   - Slots: [N] found, [M] filled, [K] unfilled (see Step 2.6 closure check)
   - Any compilation warnings
   - Path to the output `.tex` and `.pdf`

### Insertion Mechanics

When inserting after an anchor, every inserted `\footnote{}` must include the
`%CITE-PLACED` marker immediately after the opening brace:
```latex
% Anchor: "governance reform from Delaware to\nShenzhen."
% Result:
...governance reform from Delaware to
Shenzhen.\footnote{%CITE-PLACED
See Author, \textit{Title}, ...}
```

The footnote is placed immediately after the anchor string. Law review
convention: footnote marker after punctuation.

When appending to an existing footnote:
- Find the closing `}` of the existing `\footnote{...}`.
- Insert the append text before it (typically starts with `; see also`).
- Be careful with nested braces — count brace depth.

### Versioning Rules

| Original filename | Output filename |
|---|---|
| `Manuscript.tex` | `Manuscript_cited.tex` |
| `Manuscript_cited.tex` | `Manuscript_cited2.tex` |
| `Manuscript_cited2.tex` | `Manuscript_cited3.tex` |
| `My Paper.tex` | `My Paper_cited.tex` |

### Constraints
- **Never modify the original `.tex`** — always work on the copy.
- In Mode A (deterministic), if an anchor is not found, skip it. Do not guess.
- **Slots**: fill only `% CITE:` slots that have a `slot_assignments` entry;
  leave unfilled slots and every `% RESULT:` comment untouched. Run the Step 2.6
  closure check before reporting done.
- If compilation fails persistently on a specific footnote, comment it out with
  `% CITATION PLACEMENT FAILED: [reason]` and continue. Report the failure at
  the end.

---

## Phase 6 — Short-Form Post-Processing

### Goal
Convert repeated full citations to style-appropriate short forms. The first
occurrence of every source retains the full citation; all subsequent
occurrences use the style's short-form convention (Id./ibid/supra/shortened
title/author-date, depending on the selected style).

### When It Runs
Automatically after Phase 5 completes. No HITL pause between Phase 5 and
Phase 6. Operates in-place on the output `.tex` from Phase 5.

### Steps

1. Run the short-form script with the selected citation style:
   ```bash
   python "[skill-dir]/scripts/short_form.py" \
     --input "[config.output_tex]" \
     --output "[config.output_tex]" \
     --style "[config.citation_style]" \
     --skill-dir "[skill-dir]"
   ```
   The script loads the style JSON config from
   `references/styles/<citation_style>.json` for ibid/supra terms,
   hereinafter templates, et al. thresholds, and signal handling.
   Short-title generation for disambiguation uses a heuristic (first
   substantive word/phrase) that may produce suboptimal results for unusual
   titles — flagged in console output for manual review.

2. Review the console summary. If any short titles are flagged for review,
   check whether the generated short titles are clear and distinct. If not,
   manually edit the hereinafter insertions in the output `.tex`.

3. Compile with xelatex (run twice) to verify footnote numbering is correct:
   ```bash
   xelatex "[config.output_tex]"
   xelatex "[config.output_tex]"
   ```
   Two passes are needed because short forms reference footnote numbers, and
   LaTeX needs a second pass to resolve cross-references if labels changed.

### What the Script Does

**Pass 1 — Parse and index:**
- Extracts all `\footnote{...}` from the `.tex` in document order (handles
  nested braces correctly).
- Parses individual citations within each footnote (semicolon-separated).
- Extracts author key and title for each citation.
- Builds a first-occurrence map: for each unique work (identified by
  normalized author + title), records the footnote number where it first
  appears.

**Pass 2 — Detect same-author conflicts and insert disambiguation:**
- Groups works by author key. If an author has multiple distinct works
  and the style uses hereinafter (Bluebook, McGill), generates short titles
  and retroactively inserts the disambiguation marker into the first full
  citation. For Chicago, always generates short titles for subsequent refs.

**Pass 3 — Substitute short forms:**
- Walks footnotes in order. For each citation after its first occurrence,
  applies the style's short-form rules (loaded from the JSON config):
  - **Ibid/Id.** — if the style has an ibid term and conditions are met
    (immediately preceding footnote, sole citation requirements per config).
  - **Supra/cross-ref** — for all other repeated citations. Uses the style's
    supra template, which may include short titles if disambiguation was applied.

### Short-Form Rules by Style

The script reads all short-form behavior from the style JSON config at
`references/styles/<citation_style>.json`. Each style's `.md` file documents
its conventions in the "Short-Form Conventions" section. The JSON fields that
control behavior:

- `ibid_term`: The replacement text (e.g., `\textit{Id.}`, `ibid`, `Ibid.`, or null)
- `ibid_require_sole_citation`: Whether ibid can only be used as sole footnote content
- `supra_template`: Template for cross-references (e.g., `{author}, \textit{supra} note {n}`)
- `use_hereinafter`: Whether to insert disambiguation markers at first occurrence
- `et_al_threshold`: Number of authors before using et al./and others

### Edge Cases
- **Pre-existing footnotes**: The script processes ALL footnotes, not just
  pipeline-created ones.
- **Infra references**: Skipped entirely. The script does not touch footnotes
  containing "infra".
- **Discursive footnotes**: Footnotes with no recognizable citation pattern
  (no `\textit{Title}` or `\textsc{Title}`) are skipped.
- **Existing short forms**: If the manuscript already contains short-form
  markers from a prior run (supra, Id., ibid, etc.), they are recognized
  and not double-processed.

### Footnote Registry (`footnote_registry.json`)

After processing, the script saves `placement/footnote_registry.json`
containing each unique work's full citation text and metadata. This enables
`reorder_crossrefs.py` to reverse supra/Id. substitutions and re-apply them
with correct footnote numbers after manual footnotes are added.

Schema:
```json
{
  "works": {
    "<identity_key>": {
      "author_key": "Gordon",
      "title": "The Rise of Independent Directors...",
      "title_cmd": "textit",
      "short_title": "Mandatory Board Reforms",
      "needs_hereinafter": true,
      "full_citation_text": "Jeffrey N. Gordon, \\textit{The Rise of...}, 59 \\textsc{Stan.\\ L.\\ Rev.}\\ 1465 (2007) (tracing...)"
    }
  }
}
```

The registry is updated each time Phase 6 runs. It is consumed by
`scripts/reorder_crossrefs.py` for standalone cross-reference reordering.

### Reordering Cross-References After Manual Edits

If the user adds manual footnotes (without `%CITE-PLACED`) after the
pipeline runs, `\textit{supra} note N` references will point to wrong
footnotes. To fix without re-running the full pipeline:

```bash
python "[skill-dir]/scripts/reorder_crossrefs.py" \
  --input "[config.output_tex]" \
  --plan-dir "[output-dir]/placement"
```

The script:
1. Loads `footnote_registry.json` to get each work's full citation text.
2. Reverses all `\textit{supra} note N` back to full citations by matching
   author key + optional short title against the registry.
3. Reverses all `\textit{Id.}` by tracking the previous footnote's identity.
4. Strips `[hereinafter \textit{...}]` insertions (will be re-inserted).
5. Re-runs `short_form.py` to apply correct cross-references with updated
   footnote numbering.
6. Saves an updated `footnote_registry.json`.

The launcher GUI also has a "Reorder Cross-Refs" button for this operation.

---

## Restyle Pipeline

The restyle pipeline is independent of the placement pipeline. It converts
ALL existing footnote citations in a manuscript from one citation style to
another, using LLM sub-agents for the reformatting.

### When to Use

- Converting a Bluebook-formatted manuscript to OSCOLA for a UK journal
- Switching an existing manuscript's citation style without re-running
  the full placement pipeline
- Works on any footnoted manuscript — citations need not have been placed
  by the placement pipeline

### Config

The launcher writes `run_config.json` with `"pipeline": "restyle"`:

```json
{
  "pipeline": "restyle",
  "input_format": "docx",
  "input_tex": "/path/to/Manuscript.docx",
  "output_tex": "/path/to/Manuscript_oscola.docx",
  "current_style": "bluebook",
  "target_style": "oscola"
}
```

`input_format` is `"docx"` or `"tex"`. Despite the key name `input_tex`,
both formats use the same keys for consistency.

### Steps — .docx Path

When `input_format` is `"docx"`:

#### Step 1 — Copy and Extract

1. Copy the input `.docx` to `output_tex` path (non-destructive).
2. Run the extraction script to get all footnotes:
   ```python
   import sys
   sys.path.insert(0, "[skill-dir]/scripts/core")
   from docx_support.footnotes import (
       copy_docx, build_display_number_map,
       extract_footnotes_with_formatting, replace_footnote_text,
   )

   copy_docx(input_path, output_path)
   display_map = build_display_number_map(output_path)
   footnotes = extract_footnotes_with_formatting(output_path)
   ```
3. Save the extracted data to `placement/extracted.json` for reference:
   ```json
   {
     "display_map": {"id_to_display": {"1": "*", "2": "1", ...}, "offset": 1},
     "footnotes": [{"fn_id": 2, "display": "1", "text": "..."}]
   }
   ```

**Display number map**: Documents may have symbol footnotes (asterisk,
dagger, etc.) that shift the displayed numbering. `build_display_number_map`
detects these via `customMarkFollows` on `w:footnoteReference` elements.
Cross-references like "supra note N" in the manuscript use OOXML IDs, not
displayed numbers — subtract `offset` when converting to the target style's
cross-reference format (e.g., "supra note 4" with offset=1 → "(n 3)" in
OSCOLA).

#### Step 2 — Restyle Each Footnote (LLM)

Read the footnotes in batches (25–30 at a time). For each batch, read
both style `.md` files:
- `references/styles/<current_style>.md` (for parsing the input format)
- `references/styles/<target_style>.md` (for generating the output format)

For each footnote, apply the target style's rules:

1. **Parse** the citation: author(s), title, journal/publisher, volume,
   page, year, signal, parenthetical.
2. **Classify**: article, book, working paper, case, legislation,
   cross-reference (supra/Id./ibid), discursive, or internal reference.
3. **Skip** footnotes that are: pure discursive (no citation), case
   citations, legislation, or contact information.
4. **Convert internal references**: "Infra Part X" and "Supra Part X"
   are Bluebook conventions. Convert based on target style:
   - OSCOLA/Chicago: "see Part X below" / "see Part X above" (no
     trailing period for OSCOLA)
   - APA: "see Part X below" / "see Part X above"
   - McGill: "Infra" / "Supra" may be retained (McGill uses them)
   - Bluebook: retain as-is
4. **Convert cross-references**: Id./ibid to the target style's equivalent
   (e.g., Id. → ibid for OSCOLA). Supra note N → target style's convention
   (e.g., (n N) for OSCOLA), correcting the number by the display offset.
5. **Reformat** each academic citation according to the target style:
   - Rearrange element order (e.g., year before volume for OSCOLA)
   - Apply target style's author formatting (& vs and, et al. vs and others)
   - Remove or add signals as appropriate
   - Remove trailing periods if target style omits them
   - Use target style's title formatting (quotes, italics, small caps)
6. **Preserve** discursive text within mixed footnotes unchanged.
7. **Preserve** multi-citation footnotes with semicolon separation.

Write a Python script with a dict mapping `fn_id → new_text` for each
converted footnote, then apply with `replace_footnote_text`:

```python
REPLACEMENTS = {
    2: "Paul Gompers and others, 'Corporate Governance...' (2003) 118 Q J Econ 107",
    3: "ibid",
    # ... all converted footnotes
}

for fn_id, new_text in REPLACEMENTS.items():
    replace_footnote_text(output_path, fn_id, new_text)
```

`replace_footnote_text` preserves the original footnote's run formatting
(font, size, color) by cloning the base `w:rPr` from the first content run.
Formatting markers in the replacement text: `*italic*`, `**bold**`,
`^^small caps^^` are rendered as OOXML run properties.

#### Step 3 — Validate and Report

```python
from docx_support.audit_ooxml import validate_docx
diags = validate_docx(output_path)
```

Report: number converted, skipped, errors. Save changelog to
`placement/restyle_changelog.json`.

### Steps — .tex Path

When `input_format` is `"tex"`:

#### Step 1 — Copy to Output

Copy `input_tex` to `output_tex`. Never modify the original.

#### Step 2 — Reverse Short Forms (optional)

If `placement/footnote_registry.json` exists in the output directory, run
`reorder_crossrefs.py` to reverse all short forms (supra/Id./ibid) back to
full citations before restyling.

```bash
python "[skill-dir]/scripts/reorder_crossrefs.py" \
  --input "[config.output_tex]" \
  --plan-dir "[output-dir]/placement"
```

If no registry exists (hand-written manuscript), skip this step.

#### Step 3 — Restyle via LLM Sub-Agents

Split the manuscript into sections (using `\section{}`/`\subsection{}`).
For each section, spawn a sub-agent that reformats every footnote from
`current_style` to `target_style`. Each sub-agent reads the source and
target style `.md` files from `references/styles/`.

Follow the same classification and conversion rules as the .docx path
(Step 2 above), but output LaTeX-formatted footnote content with
`\textit{}`, `\textsc{}`, etc.

**Sub-agent output format** — for each modified footnote:
- **Anchor**: verbatim text immediately before the `\footnote{`
- **Old footnote**: original content
- **New footnote**: restyled content
- **Changes**: brief description

Spawn all section agents in parallel. Name each `restyle-section-[ID]`.

#### Step 4 — Apply Replacements

For each sub-agent's output, apply replacements using exact anchor
matching. Process in reverse document order to preserve character offsets.
Preserve `%CITE-PLACED` markers if present.

#### Step 5 — Post-Processing

```bash
python "[skill-dir]/scripts/merge_adjacent_footnotes.py" \
  --input "[config.output_tex]" \
  --output "[config.output_tex]" \
  --style "[config.target_style]" \
  --skill-dir "[skill-dir]"

python "[skill-dir]/scripts/short_form.py" \
  --input "[config.output_tex]" \
  --output "[config.output_tex]" \
  --style "[config.target_style]" \
  --skill-dir "[skill-dir]"
```

#### Step 6 — Compile

```bash
xelatex "[config.output_tex]"
xelatex "[config.output_tex]"
```

### Constraints

- **Never modify the original manuscript** — always work on the output copy.
- **Preserve non-citation footnotes**: discursive footnotes, case citations,
  and legislation pass through unchanged.
- **Convert internal references**: "Infra Part X" / "Supra Part X" must be
  converted to the target style's convention (e.g., "see Part X below" /
  "see Part X above" for OSCOLA). These are NOT skipped.
- **Cross-reference number correction**: Always check for symbol footnotes
  (asterisk, dagger) via `build_display_number_map` and correct cross-reference
  numbers by the offset.
- **One section per sub-agent** (.tex path): keeps generation volume manageable.
- **Batch processing** (.docx path): process 25–30 footnotes at a time to
  stay within manageable context.
