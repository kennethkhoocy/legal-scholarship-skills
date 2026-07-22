# Phase Details — Citation Placement (Inline `\cite{}`)

Detailed instructions for each phase of the **inline mode** of the
`cite-placement` skill (inline `\cite{}` / `\citet{}` / `\citep{}` with a
compiled `.bib`). Read only the section relevant to the phase you are currently
executing.

## Table of Contents

0. [Launcher](#launcher)
1. [Phase 1 — Manuscript Mapping](#phase-1--manuscript-mapping)
1.5. [Phase 1.5 — Existing Citation Verification](#phase-15--existing-citation-verification)
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
Collect file paths and options from the user via a Tkinter GUI before running
the pipeline.

### Steps

1. Run the launcher with a **10-minute timeout** (the user needs time to browse
   and configure):
   ```bash
   python "[skill-dir]/scripts/launcher.py"
   ```
   Use `timeout: 600000` when calling via the Bash tool. The `[skill-dir]` is
   the absolute path to the `cite-placement/` directory — use the skill's known
   location, not the current working directory.
2. The GUI presents file fields (Project Folder, Input .tex, Input .xlsx,
   Output .tex), dropdowns (Citation Style, Placement Plan, HITL Review,
   Citation Mode, Insertion Style), and a Citation Verification checkbox. When
   the user clicks **Inline Placement**, the launcher writes `run_config.json`
   with `"pipeline": "inline"`.
3. On run, the launcher validates inputs and writes `placement/run_config.json`
   in the **output .tex file's parent directory** with all resolved absolute
   paths, then prints machine-readable status to stdout. On cancel or window
   close it prints `LAUNCHER_STATUS: cancelled`.
4. Parse the launcher's stdout to get the config path:
   - Look for `LAUNCHER_STATUS: success` — if missing or `cancelled`, stop.
   - Look for `LAUNCHER_CONFIG_PATH: <path>` — the absolute path to
     `run_config.json`. Use this path for all subsequent phases.
5. Read `run_config.json` at the start of each subsequent phase to get paths:
   ```python
   import json
   from pathlib import Path
   config = json.loads(Path("<config_path>").read_text())
   # config["pipeline"]          — str ("inline")
   # config["input_format"]      — str ("tex")
   # config["project_folder"]    — str or null
   # config["input_tex"]         — str (absolute path)
   # config["input_xlsx"]        — str (absolute path)
   # config["output_tex"]        — str (absolute path)
   # config["citation_style"]    — str (e.g., "apa", "mla", "harvard")
   # config["replan"]            — bool
   # config["auto_approve"]      — bool
   # config["citation_mode"]     — str ("selective" or "comprehensive")
   # config["insertion_style"]   — str ("prose" or "simple")
   # config["verify_citations"]  — bool
   ```
   **Important**: All paths in `run_config.json` are absolute. Do not assume the
   config is in the current working directory — always use the absolute path
   from `LAUNCHER_CONFIG_PATH`.

---

## Phase 1 — Manuscript Mapping

### Goal
Build a detailed paragraph-level map of the manuscript to guide citation
placement, and detect the citation package used by the manuscript.

### Cache Check

Before doing any work, read `replan` from `run_config.json`:
- If `replan` is `false` and `placement/section_map.md` exists → skip this
  phase. Print "Using cached section map." If the input `.tex` file is newer
  than `section_map.md`, also print: "Note: manuscript has been modified since
  the section map was generated. Using cached version. Select 'Force regenerate'
  to rebuild."
- If `replan` is `true` → regenerate regardless.

### Steps

1. Read the entire `.tex` manuscript.
2. **Detect citation package** from the preamble:
   - Search for `\usepackage{natbib}` or `\usepackage[...]{natbib}` → `natbib`
   - Search for `\usepackage{biblatex}` or `\usepackage[...]{biblatex}` → `biblatex`
   - Neither found → `basic`
   - Record the detected package for all downstream phases.
3. **Detect bibliography backend**:
   - If `biblatex` is loaded, check for `backend=biber` (default) or
     `backend=bibtex`. Default to `biber` if not specified.
   - If `natbib` or basic → use `bibtex`.
4. Create directory `placement/` if it doesn't exist.
5. Produce `placement/section_map.md` with the following structure:

```markdown
# Manuscript Map: [Manuscript Title]

**Citation package**: natbib | biblatex | basic
**Bibliography backend**: bibtex | biber
**Existing cite commands found**: \citet, \citep (list all variants seen)

## Section 1 — [Section Title]

### Subsection 1.1 — [Subsection Title]

#### Paragraph 1 (starting with "[first ~8 words]...")
- **Argument/claim**: [What this paragraph argues or establishes]
- **Mechanisms/variables**: [Key concepts, variables, or theories invoked]
- **Existing citations**:
  - \citet{gordon2006rise} — "Gordon (2006) argues that..." — supports [Y]
  - \citep{adams2010role, hermalin2003boards} — end of sentence — supports [Z]
- **Existing footnotes** (if any):
  - Footnote 2 [discursive]: "The median figure is computed from..."

#### Paragraph 2 (starting with "[first ~8 words]...")
...
```

### What to Record

For every paragraph:
- The **specific claim or argument** — not just "discusses X" but "argues that
  mandatory disclosure increases firm value through reduced information
  asymmetry."
- **All mechanisms, variables, and concepts** invoked (e.g., "information
  asymmetry", "bid-ask spread", "voluntary disclosure").
- **Every existing `\cite{}` / `\citet{}` / `\citep{}` command** with: the
  cite key(s), how it appears in the text, and what claim it supports.
- **Footnotes** (if any): economics papers sometimes have content footnotes
  alongside inline cites. Classify each as: `discursive` (author commentary),
  `cross_reference` (see Section X), or `citation` (contains a `\cite{}`
  command inside the footnote).
- **Equations and formal results**: Note them briefly — citations near formal
  results often support the derivation methodology or assumptions.

### Structured Extraction: `existing_citations.json`

In addition to `section_map.md`, produce
`placement/existing_citations.json` — a structured extraction of all
existing `\cite{}` commands found in the manuscript:

```json
{
  "citation_package": "natbib",
  "bibliography_backend": "bibtex",
  "cite_commands_used": ["\\citet", "\\citep", "\\cite"],
  "existing_bib_file": "references.bib",
  "citations": [
    {
      "cite_key": "gordon2006rise",
      "command": "\\citet",
      "section_id": "I",
      "paragraph_start": "Corporate boards have a fixed...",
      "context": "Gordon (2006) argues that board independence...",
      "claim_supported": "rise of independent directors"
    }
  ]
}
```

This extraction always runs regardless of the `verify_citations` flag — it is
lightweight (part of the mapping pass) and useful for Phase 3 context even
without verification.

### Citation Slots (`% CITE:`)

Drafts produced by the `writing-article-plans` skill mark intended citation
sites with typed placeholder slots — `% CITE:` LaTeX comments carrying a hint
(e.g. `% CITE: meta-analysis on Y`, `% CITE: study establishing X`). A slot is
an author-declared demand for a citation, distinct from any `\cite{}` command
already in the manuscript. While mapping, enumerate **every** `% CITE:` slot.
Three forms occur:

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

Record every slot in `existing_citations.json` under a new top-level array
`citation_slots` (shown here alongside the `citations` array it sits beside):

```json
{
  "citations": [ "...the existing-citation entries shown above..." ],
  "citation_slots": [
    {
      "slot_id": "S1",
      "section": "II",
      "anchor": "% CITE: meta-analysis on Y",
      "hint": "meta-analysis on Y",
      "form": "bare"
    }
  ]
}
```

The `anchor` is the exact `% CITE:` comment line, verbatim — for a footnote-wrapped
slot it is the inner `% CITE: <hint>` line, never the surrounding `\footnote{…}`
shell. The `form` field records whether that line sits inside a footnote shell, so
Phase 5 can locate the slot deterministically and know how to fill it.
Slots do **not** count as existing citations — they are demands to be filled, not
`\cite{}` commands already present, and never appear in the `citations` array.
Report the slot count in the Phase 1 console summary (e.g. "Found 7 `% CITE:`
slots (3 bare, 4 footnote-wrapped)"). Leave `% RESULT:` comments untouched —
they belong to a different pipeline.

### Why This Matters

Phase 3 uses this map to decide where each new citation belongs. A vague map
("this section discusses corporate governance") leads to vague placements. A
precise map ("Paragraph 3 argues that board independence reduces tunneling,
citing \citet{shleifer1997survey} for the theoretical mechanism") lets Phase 3
place a new tunneling citation with confidence.

### Constraints
- **Read-only**: Do not modify the `.tex` file or any other source file.
- Record the map accurately — do not invent content that isn't in the manuscript.
- If the manuscript has no section structure (flat document), use paragraph
  numbering as the organizing unit.

---

## Phase 1.5 — Existing Citation Verification

### Goal
Verify existing `\cite{}` references in the manuscript against the `.bib` file
and external APIs. Detect dangling references, hallucinated bib entries, and
overlaps with the incoming RA spreadsheet.

### Gate Check

Read `verify_citations` from `run_config.json`:
- If `false` (default): skip this phase entirely. Print "Citation verification
  disabled — skipping Phase 1.5."
- If `true`: proceed with the full verification.

### Steps

1. Read `placement/existing_citations.json` (produced by Phase 1).
2. Run the verification script:
   ```bash
   python "[skill-dir]/scripts/core/verify_citations.py" \
     --mode inline \
     --citations "[output-dir]/existing_citations.json" \
     --bib "[path-to-existing-bib]" \
     --output "[output-dir]/audit_report.json" \
     --spreadsheet "[config.input_xlsx]"
   ```
3. Review console output. If dangling references or hallucinated bib entries
   are flagged, print them prominently.

### Verification Steps

The script performs three checks:

1. **Dangling references**: `\cite{key}` commands in the `.tex` where `key`
   does not exist in any `.bib` file. These cause compilation errors.
2. **Bib entry verification**: For each entry in the `.bib`, verify against
   OpenAlex → CrossRef → Google Scholar (SearchAPI, optional via
   `SEARCHAPI_API_KEY`). Flag hallucinated entries.
3. **Overlap with RA spreadsheet**: If the incoming spreadsheet contains papers
   already in the `.bib`, flag them. The RA version's metadata wins.

### Output: `placement/audit_report.json`

```json
{
  "summary": {
    "total_cite_commands": 45,
    "unique_keys": 38,
    "dangling_references": 2,
    "bib_entries_verified": 36,
    "bib_entries_unverified": 2,
    "bib_entries_hallucinated": 0,
    "overlaps_with_spreadsheet": 3
  },
  "dangling": [
    {"cite_key": "smith2024missing", "locations": ["Section I, para 3"]}
  ],
  "bib_entries": [
    {
      "cite_key": "gordon2006rise",
      "status": "verified",
      "verified_via": "openalex",
      "verified_doi": "10.2139/ssrn.abc"
    }
  ],
  "overlaps": [
    {
      "cite_key": "adams2010role",
      "spreadsheet_title": "The Role of Boards of Directors...",
      "action": "update_metadata"
    }
  ]
}
```

### How Downstream Phases Use the Audit

**Phase 3a**: If `audit_report.json` exists, read it. Hallucinated bib entries
do not count as "already cited." Overlapping citations are noted as "update
metadata with RA version" rather than skipped. If `audit_report.json` does not
exist, treat all existing citations as valid.

**Phase 5**: If `audit_report.json` exists, apply fixes:
- **Dangling references**: Print warning. Do not auto-remove (user may want to
  fix the `.bib` instead).
- **Hallucinated bib entries**: Remove from the merged `.bib`. Print warning.
- **Overlaps**: Replace bib entry metadata with RA spreadsheet version.
- **Unverified**: Leave untouched, print warning for manual review.

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
   Omit `--existing-bib` if no existing `.bib` file was found.
   Optional: `--min-score N` skips spreadsheet rows whose `screening_score` is below N (default 0 = no filtering).
4. Review the console summary (N ingested, N duplicates, N written).

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

### BibTeX Entry Type Mapping

| Condition | Entry Type |
|---|---|
| Has journal | `@article` |
| Has publisher, no journal | `@book` |
| Has booktitle | `@incollection` |
| SSRN/NBER/working paper indicators | `@techreport` |
| None of the above | `@unpublished` |

### Cite Key Format

Google Scholar style: `lastnameYEARfirstword`
- e.g., `mackinlay1997event`
- Multi-author: use first author's last name only
- Collision: append `b`, `c`, etc.

### Duplicate Detection

When `--existing-bib` is provided:
1. Match on DOI only (exact, case-insensitive, URL prefixes stripped)
2. If no DOI on either side, no match is attempted
3. Duplicates are flagged `"already_in_bib": true` in JSON
4. Duplicates are excluded from `.bib` output but retained in JSON

---

## Phase 3 — Placement Planning (Agentic Hybrid)

### Goal
Determine exactly where each new citation should be placed, specify the cite
command type (`\citet{}`, `\citep{}`, or `\cite{}`), and record a **verbatim
anchor string** for deterministic insertion.

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
1. If `placement_plan.md` does not exist → run from scratch.
2. If `placement_plan.md` exists:
   a. Read the `planned_keys` header.
   b. Load `citations.json` from Phase 2.
   c. Diff: find cite keys in `citations.json` not in `planned_keys`.
   d. If no new citations → skip Phase 3. Print: "No new citations to plan."
   e. If new citations exist → incremental: 3a assigns only new keys, 3b
      spawns agents only for affected sections, 3c appends to existing plan.

### `planned_keys` Header

The first line of `placement_plan.md` must be an HTML comment listing all cite
keys that have placements in the plan:

```
<!-- planned_keys: gordon2006rise, adams2010role, gilson2001globalizing -->
```

---

### Phase 3a — Assignment

#### Goal
Produce a lightweight assignment mapping — which citations go where — in a
single LLM pass. Citations can be assigned to **multiple sections**. The same
source routinely appears 2–4 times across an economics article (e.g.,
introduced in the literature review, cited again in the empirical strategy,
and once more in the discussion).

Phase 3a operates in one of two modes, controlled by `citation_mode` in
`run_config.json`:
- **`selective`** (default): Each placement must attach to a specific claim.
  Weak placements are dropped but strong placements in multiple sections are
  kept. At each location, if multiple citations support the same claim, keep
  the strongest 1-2. Do not cull aggressively — economics papers are well-cited,
  typically 40-80 references. When in doubt, place.
- **`comprehensive`**: Place at every relevant location. The only valid skip
  reason is `already_cited`.

#### Input
- `placement/section_map.md`
- `placement/citations.json`
- The `.tex` manuscript
- `citation_mode` from `run_config.json`
- `placement/audit_report.json` (if exists)

#### Slot Pass (mandatory — runs before ordinary assignment)

If `existing_citations.json` contains a non-empty `citation_slots` array, a
mandatory slot pass runs **before** the ordinary assignment steps below. Each
slot is an author-declared citation demand and must be resolved; it is not
subject to selective culling.

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
   record the slot in the `unfilled_slots` array (schema below) with a concrete
   `reason` (e.g. "no meta-analysis on Y in spreadsheet").

Every slot ends the pass either assigned one or more cite keys (in
`slot_assignments`) or listed in `unfilled_slots`. `citation_mode` does not
apply to slots — `selective` governs only free placements and never skips a
slot.

#### Steps

1. Load all inputs into a single context.
2. For each citation in `citations.json` (excluding `already_in_bib: true`
   unless the citation appears uncited in the manuscript):
   - Use `relevance_note`, `relationship`, `screening_rationale`, and
     `abstract` to understand what the citation contributes.
   - **Scan every section** for paragraphs where the same argument, mechanism,
     or variable is discussed. Do not stop after the first match.
   - For each matching location, record the target paragraph, cite command
     type, integration phrase, and `placement_strength`.
3. Cross-reference against existing `\cite{}` commands in `section_map.md`.
   If a cite key already appears in the manuscript, place in `skipped` with
   reason `"already_cited"`.
   **Audit override**: If `audit_report.json` exists, hallucinated bib entries
   do NOT count as already cited. Overlaps are noted as "update metadata"
   rather than skipped.

#### Cite Command Selection

For each placement, specify the cite command type based on how the citation
integrates with the sentence. Read the citation package from `section_map.md`
and use the correct command variant:

| Integration | natbib | biblatex | basic |
|---|---|---|---|
| Author is grammatical subject | `\citet` | `\textcite` | `\cite` |
| Parenthetical at end of claim | `\citep` | `\parencite` | `\cite` |
| Generic / ambiguous | `\cite` | `\cite` | `\cite` |

#### Output: `placement/assignment.json`

```json
{
  "citation_package": "natbib",
  "assigned_citations": [
    {
      "cite_key": "gordon2006rise",
      "placements": [
        {
          "section_id": "I",
          "target_paragraph": "paragraph starting with '...'",
          "cite_command": "\\citet",
          "integration": "textual, subject of sentence introducing independence literature",
          "placement_strength": "strong"
        },
        {
          "section_id": "IV",
          "target_paragraph": "paragraph starting with '...'",
          "cite_command": "\\citep",
          "integration": "parenthetical, supporting claim about convergence",
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
      "form": "bare",
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
    }
  ],
  "stats": {
    "total_citations": 95,
    "citations_with_placements": 78,
    "total_placements": 120,
    "multi_placement_citations": 28,
    "multi_placement_rate": 0.36,
    "skipped": 17,
    "citation_mode": "selective"
  }
}
```

#### Validation

Every citation in `citations.json` must appear in either `assigned_citations`
or `skipped`. Print summary: "Assigned [N] citations ([P] total placements,
[M] multi-placement) across [S] sections. Skipped [K]. Total: [N+K]/[total]."

Also validate slots: every slot in `citation_slots` must appear in either
`slot_assignments` or `unfilled_slots`. Print a slot line: "Slots: [N] found,
[M] filled, [K] unfilled."

---

### Phase 3b — Detailed Planning (per-section sub-agents)

#### Goal
For each section with assigned citations, spawn a sub-agent that writes the
full placement entries (anchors, cite commands, integration text). Each
sub-agent handles ~20–40 citations. Sub-agents run in parallel.

#### Insertion Style Gate

Read `insertion_style` from `run_config.json` before constructing the
sub-agent prompt:
- `"prose"` → use the **Prose-Integrated Template** below (Types 1/2/3,
  prose rewriting rules, 60/30/10 guideline).
- `"simple"` → use the **Simple Template** below (Type 1 only, no prose
  rewriting, mechanical insertion).

#### Input per sub-agent
1. The full `section_map.md` (for global awareness of paper structure).
2. The **full text** of its assigned section from the `.tex` file.
3. The full metadata (from `citations.json`) for every citation that has a
   placement in this section.
4. The placement entries for this section from `assignment.json`.
5. A list of all existing `\cite{}` commands in its section.
6. In incremental mode: existing plan entries for its section.
7. Any `slot_assignments` entries whose `section` is this section, each with its
   `slot_id`, `anchor`, `hint`, slot `form`, and assigned `cite_keys`.

---

#### Slot Placements (both templates — listed first)

Slot handling applies under both the Simple and Prose templates. If the section
has `slot_assignments` entries (from Phase 3a), the sub-agent lists them
**first** in its output, before any free placement, each as a placement entry
with placement type `slot`:

- **Type**: `slot`
- **Slot form**: `bare` | `footnote_two_line` | `footnote_one_line`
- **Anchor**: the exact `% CITE: <hint>` comment line to locate. For a `bare`
  slot, that comment (extend with the preceding sentence if needed to make it
  unique). For a footnote-wrapped slot, the `% CITE: <hint>` comment line inside
  the braces, never the surrounding `\footnote{…}` shell.
- **Replace slot with**: the complete replacement text — the cite command
  (`\citep{}` / `\citet{}` / `\cite{}` per the package rules) built from the
  slot's assigned `cite_keys`. For a footnote-wrapped slot the anchor line only
  locates the slot; Phase 5 replaces the **entire** enclosing `\footnote{…}`
  shell with the cite command, since author-date journals do not take citation
  footnotes.
- **Status**: new
- **Cite keys**: the assigned keys.

Slots listed in `unfilled_slots` are **not** placed; they are carried to the
Phase 4 report and left untouched in the manuscript.

Example (inline):
```markdown
### Slot S1 (hint: "meta-analysis on Y")
- **Type**: slot
- **Slot form**: bare
- **Anchor**: "% CITE: meta-analysis on Y"
- **Replace slot with**: \citep{smith2020meta, jones2019review}
- **Status**: new
- **Cite keys**: smith2020meta, jones2019review
```

---

#### Simple Template (`insertion_style: "simple"`)

Use this template when `insertion_style` is `"simple"`. All placements are
Type 1 (parenthetical). No sentence rewriting.

```
You are placing citations as inline \cite{} commands in one section of an
academic paper. Your task is mechanical: append cite commands after the
sentences they support. Do not rewrite any prose.

## Your section
Section [SECTION_ID]: [SECTION_TITLE]
Lines [START]–[END] of the manuscript.

## Citation package
[natbib / biblatex / basic] — use [commands] accordingly.

## Section text
[SECTION_TEX_CONTENT]

## Citations to place
[CITATION_METADATA_JSON — only entries assigned to this section]

## Assignment guidance from Phase 3a
[ASSIGNMENT_ENTRIES_FOR_THIS_SECTION]

## Existing citations in this section
[EXISTING_CITATIONS_LIST — from section_map.md]

## Instructions
For each assigned citation, identify the anchor point — the end of the
sentence or clause that the citation supports — and specify the cite command
to insert after it.

### Rules
- **All placements are Type 1 (parenthetical).** Use only `**Insert after
  anchor**`, never `**Replace anchor with**`.
- **Default command is `\citep{key}`** (parenthetical at end of sentence or
  clause).
- **Use `\citet{key}` only** when the Phase 3a assignment explicitly
  specifies a textual cite — i.e., the author is already named in the
  sentence and just needs the year reference.
- **Combine multiple citations at the same location** into a single command:
  `\citep{key1, key2, key3}`.
- **Do not rewrite any text.** The existing prose is preserved unchanged.
- Copy the anchor EXACTLY from the .tex, including LaTeX commands.
- The anchor must be UNIQUE within the .tex file.

## Output format

### Paragraph N (starting with "[first ~8 words]...")
- **Type**: parenthetical
- **Anchor**: "exact verbatim text from .tex ending at insertion point."
- **Insert after anchor**: \citep{key1, key2}
- **Justification**: [1 sentence]
- **Status**: new
- **Cite keys**: key1, key2

Every assigned citation must appear in your output. Print a count at the end:
"Section [ID]: [N] placements for [M] assigned citations."
```

---

#### Prose-Integrated Template (`insertion_style: "prose"`)

Use this template when `insertion_style` is `"prose"` (the default). Sub-agents
choose among three placement types and may rewrite sentences.

```
You are placing citations as inline \cite{} commands in one section of an
academic paper. Your goal is to produce placements that read like a human
scholar wrote them — citations woven into the prose, not mechanically stapled
to sentence ends.

## Your section
Section [SECTION_ID]: [SECTION_TITLE]
Lines [START]–[END] of the manuscript.

## Citation package
[natbib / biblatex / basic] — use [commands] accordingly.

## Full paper structure (for context only — do not place citations outside your section)
[SECTION_MAP_CONTENT]

## Section text
[SECTION_TEX_CONTENT]

## Citations to place
[CITATION_METADATA_JSON — only entries assigned to this section]

## Assignment guidance from Phase 3a
[ASSIGNMENT_ENTRIES_FOR_THIS_SECTION]

## Existing citations in this section
[EXISTING_CITATIONS_LIST — from section_map.md]

## Existing plan entries for this section (incremental mode only)
[EXISTING_PLAN_ENTRIES — if any; omit if full regenerate]

## Instructions
For each assigned citation, choose a placement type and produce a placement
entry. The three types are described below.

### Three placement types

**Type 1 — Simple parenthetical (`parenthetical`)**
The citation is appended after existing text. The anchor text is preserved
unchanged. Use this when the manuscript already makes a complete claim and the
citation is pure support.

Example:
- **Type**: parenthetical
- **Anchor**: "consistent with the broader literature on board independence"
- **Insert after anchor**: \citep{gordon2006rise, adams2010role}

**Type 2 — Prose integration (`prose`)**
The citation is woven into the sentence. The anchor text is replaced with a
rewritten version that incorporates citations at natural break points. Use this
when multiple citations support different parts of a compound claim, or when a
connecting phrase is needed.

Example:
- **Type**: prose
- **Anchor**: "The number of publicly listed firms has declined sharply across developed markets, driven in part by the collapse of small-company IPO activity."
- **Replace anchor with**: "The number of publicly listed firms has declined sharply across developed markets \citep{doidge2017eclipse}, driven in part by the collapse of small-company IPO activity \citep{gao2013growth}."

**Type 3 — Textual citation (`textual`)**
The cited author becomes the grammatical subject or actor in the sentence. The
anchor text is replaced. Use this for foundational works, methodological
references, or when the author's identity matters to the argument.

Example:
- **Type**: textual
- **Anchor**: "Prior work establishes that legal institutions and investor protection shape financial development."
- **Replace anchor with**: "\citet{laporta1998law} establish that legal institutions and investor protection shape financial development, a finding extended to securities regulation by \citet{laporta2006securities}."

### When to use each type

**Use Type 1 (parenthetical) when:**
- The sentence already makes a complete, well-formed claim.
- The citation is pure support — adding it doesn't change the sentence.
- Multiple citations all support the same undivided claim (combine as
  \citep{key1, key2, key3}).
- The placement is at the end of a sentence or clause.

**Use Type 2 (prose) when:**
- Multiple citations support different parts of a compound sentence (each gets
  its own \citep{}).
- A connecting phrase is needed between the claim and the citation (e.g., "as
  documented by", "a pattern consistent with").
- The sentence needs minor restructuring to accommodate citations at natural
  break points rather than all at the end.

**Use Type 3 (textual) when:**
- The cited author is making a specific, named contribution that the manuscript
  builds on (e.g., "Following \citet{...}, we define...").
- The citation is to a foundational or methodological work whose authorship
  matters.
- The manuscript explicitly engages with the cited author's argument (agrees,
  disagrees, extends).

**Distribution guideline**: In a typical economics/finance paper, expect
roughly 60% Type 1, 30% Type 2, 10% Type 3. If you are producing 90%+ Type 1,
you are being too conservative — look for opportunities for prose integration.
If you are producing 50%+ Type 2/3, you are being too aggressive — most
citations are straightforward parenthetical support.

### Prose rewriting rules (Type 2 and Type 3)

These rules are critical. Violating them changes the author's manuscript in
ways they did not ask for.

1. **Preserve the author's claim exactly.** The rewrite integrates citations
   into the sentence structure but does NOT change what the sentence asserts.
   The factual content, argument direction, and rhetorical force must be
   identical before and after.

2. **Minimize changes.** The rewrite should be the smallest edit that produces
   natural prose. Do not restructure paragraphs, combine sentences, or rewrite
   beyond the immediate sentence containing the citation.

3. **The anchor must be long enough to be unique.** For Type 2/3, the anchor is
   the full sentence or clause being rewritten. It must be a verbatim, unique
   substring of the .tex.

4. **The replacement must be complete.** The replacement text includes
   everything — the rewritten prose, the cite commands, punctuation. Phase 5
   does a direct string substitution.

5. **Do not invent claims.** If the citation supports a finding that the
   manuscript doesn't mention, do NOT add that finding to the prose. Place the
   citation parenthetically (Type 1) instead.

6. **Respect the author's voice.** If the manuscript uses formal/passive voice,
   the rewrite should too. If the manuscript uses first person ("we show"),
   maintain it. Do not shift register.

### Cite command rules

**Textual citation** — author name is part of the sentence grammar:
- "Following \citet{gordon2006rise}, we define..."
- "\citet{mackinlay1997event} introduces the standard methodology."

**Parenthetical citation** — citation in parentheses at end of claim:
- "...consistent with the independence hypothesis \citep{gordon2006rise}."
- "...as documented in the literature \citep{adams2010role, hermalin2003boards}."

**Grouping**: If 2+ citations support the same claim at the same location,
combine into one command: \citep{key1, key2, key3}. Do NOT write
\citep{key1} \citep{key2} separately. If they support different parts of the
sentence, use Type 2 (prose) and place each at its natural location.

### Anchor rules
- Copy the anchor EXACTLY from the .tex, including LaTeX commands and line
  breaks.
- The anchor must be UNIQUE within the .tex file.
- For Type 1: use the last clause or sentence before the insertion point. The
  anchor must NOT include an existing \cite{} command at the insertion point.
- For Type 2/3: the anchor is the full sentence (or multi-sentence span) being
  rewritten. It must be long enough to be unique in the .tex.

## Output format
Write your output as markdown with this structure:

## Section [SECTION_ID] — [SECTION_TITLE]

[Type 1 — simple parenthetical:]
### Paragraph N (starting with "[first ~8 words]...")
- **Type**: parenthetical
- **Anchor**: "exact verbatim text from .tex ending at insertion point."
- **Insert after anchor**: \citep{gordon2006rise, adams2010role}
- **Justification**: [1-2 sentences]
- **Status**: new
- **Cite keys**: gordon2006rise, adams2010role

[Type 2 — prose integration:]
### Paragraph N (starting with "[first ~8 words]...")
- **Type**: prose
- **Anchor**: "The number of publicly listed firms has declined sharply across developed markets, driven in part by the collapse of small-company IPO activity."
- **Replace anchor with**: "The number of publicly listed firms has declined sharply across developed markets \citep{doidge2017eclipse}, driven in part by the collapse of small-company IPO activity \citep{gao2013growth}."
- **Justification**: [1-2 sentences]
- **Status**: new
- **Cite keys**: doidge2017eclipse, gao2013growth

[Type 3 — textual citation:]
### Paragraph N (starting with "[first ~8 words]...")
- **Type**: textual
- **Anchor**: "Prior work establishes that legal institutions and investor protection shape financial development."
- **Replace anchor with**: "\citet{laporta1998law} establish that legal institutions and investor protection shape financial development, a finding extended to securities regulation by \citet{laporta2006securities}."
- **Justification**: [1-2 sentences]
- **Status**: new
- **Cite keys**: laporta1998law, laporta2006securities

Every assigned citation must appear in your output. Print a count at the end:
"Section [ID]: [N] placements ([P1] parenthetical, [P2] prose, [P3] textual)
for [M] assigned citations."
```

#### Output: `placement/section_plans/section_[ID].md`

Each sub-agent writes its output to a separate file.

#### Spawning

Use the Claude Code `Agent` tool with `subagent_type: "general-purpose"` for
each section. Spawn all section agents in a single message for parallel
execution. Name each agent `cite-3b-section-[ID]` so progress can be tracked.

---

### Phase 3c — Consolidation

#### Goal
Merge all per-section plans into a single `placement_plan.md`, validate
completeness, and handle any cross-section issues.

#### Steps

1. Read all section plan files.
2. Order sections by manuscript sequence.
3. **Keep all placements.** Do NOT deduplicate across sections. A cite key
   appearing in Section I and Section IV stays in both places — this is normal
   for academic papers.
4. Write the `planned_keys` HTML comment header at the top.
5. Append the `## Skipped Citations` section from `assignment.json`.
6. Write to `placement/placement_plan.md`.
7. Print summary.

#### Validation

Every citation in `citations.json` must appear in either the plan or the
skipped list. Print an error if any are missing.

#### Output: `placement/placement_plan.md`

```markdown
<!-- planned_keys: gordon2006rise, gilson2001globalizing, doidge2017eclipse, gao2013growth, laporta1998law -->
# Placement Plan

## Section I — [Section Title]

### Paragraph 3 (starting with "[first ~8 words]...")
- **Type**: parenthetical
- **Anchor**: "the organizing principle of governance reform across jurisdictions."
- **Insert after anchor**: \citep{gilson2001globalizing}
- **Justification**: [1-2 sentences]
- **Status**: new
- **Cite keys**: gilson2001globalizing

### Paragraph 4 (starting with "[first ~8 words]...")
- **Type**: prose
- **Anchor**: "The number of publicly listed firms has declined sharply across developed markets, driven in part by the collapse of small-company IPO activity."
- **Replace anchor with**: "The number of publicly listed firms has declined sharply across developed markets \citep{doidge2017eclipse}, driven in part by the collapse of small-company IPO activity \citep{gao2013growth}."
- **Justification**: [1-2 sentences]
- **Status**: new
- **Cite keys**: doidge2017eclipse, gao2013growth

### Paragraph 5 (starting with "[first ~8 words]...")
- **Type**: textual
- **Anchor**: "Prior work establishes that legal institutions shape financial development."
- **Replace anchor with**: "\citet{laporta1998law} establish that legal institutions shape financial development."
- **Justification**: [1-2 sentences]
- **Status**: new
- **Cite keys**: laporta1998law

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

### Section I — Paragraph 2 (starting with "[first ~8 words]...")
- **Type**: parenthetical
- **Anchor**: "advisory contract cannot replicate."
- **Insert after anchor**: \citep{newauthor2025example}
- **Justification**: ...
- **Status**: new
- **Cite keys**: newauthor2025example
```

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
   free-placement summary.

3. **If `auto_approve` is `false`** (default):
   - Tell the user:
     > "I've created the placement plan at `placement/placement_plan.md`.
     > Please review it and let me know:
     > - Any placements to **remove** (citation doesn't belong there)
     > - Any placements to **move** (right citation, wrong location)
     > - Any cite commands to **change** (e.g., \citet → \citep)
     > - Any **additional citations** you want placed that I missed
     > - Any changes to **grouping** (combine/split multi-cite commands)
     > - Any **unfilled `% CITE:` slots** to resolve (point me at the right
     >   source, or confirm leaving the gap)
     >
     > When you're satisfied, tell me to proceed with Phase 5."
   - Wait for the user's response. Do not proceed until explicitly told to.

4. **If `auto_approve` is `true`**:
   - Print: "Auto-approve enabled — proceeding to Phase 5."
   - Continue immediately.

### Why This Checkpoint Exists

Citation placement is a scholarly judgment call. The LLM can get the mechanics
right (formatting, grouping, deduplication) but the author knows which
citations truly strengthen their argument at each point.

---

## Phase 5 — Execution

### Goal
Insert cite commands into a new copy of the manuscript, merge the `.bib` file,
ensure bibliography infrastructure is correct, and compile.

### Step 1 — Create Output File

1. **Copy the manuscript** to the output path specified in `run_config.json`.
   - Default: `{name}_cited.tex`
   - If the output file already exists: overwrite it (it's a derived file).
   - **Never modify the original `.tex`.**

### Step 2 — Apply Audit Fixes (if audit_report.json exists)

If `placement/audit_report.json` exists, read it and apply fixes:

1. **Dangling references**: Print warning with the dangling keys. Do not
   auto-remove from `.tex` — the user may want to add the entry to `.bib`
   instead.
2. **Hallucinated bib entries**: Remove from the merged `.bib`. Print warning.
3. **Overlaps**: Update `.bib` entry metadata with RA spreadsheet version.
4. **Unverified**: Leave untouched, print warning.

### Step 3 — Merge `.bib` File

1. Read the project's existing `.bib` file (detected in Phase 1 or found by
   scanning the project directory).
2. Read `references_new.bib` from Phase 2.
3. Merge: for each entry in `references_new.bib`:
   - If the cite key already exists in the main `.bib` → skip (do not
     overwrite unless flagged as overlap in audit).
   - Otherwise → append to the main `.bib`.
4. Write the merged `.bib` file. If no existing `.bib` was found, create one
   (e.g., `references.bib`) in the project directory.

### Step 4 — Ensure Bibliography Infrastructure

Check the output `.tex` for:

1. **`\bibliographystyle{}`**: If missing, add before `\end{document}` using
   the style from `run_config.json`:
   - `apa` → `\bibliographystyle{apalike}`
   - `mla` → `\bibliographystyle{mla}`
   - `harvard` → `\bibliographystyle{agsm}`
   - `chicago_author_date` → `\bibliographystyle{chicago}`
   - `chicago_notes` → `\bibliographystyle{chicago-notes}` (print warning:
     "Chicago Notes style uses footnotes — use footnotes mode instead.")
   - `ieee` → `\bibliographystyle{IEEEtran}`
   - `vancouver` → `\bibliographystyle{vancouver}`

   If it already exists, check for consistency with the selected style. If
   mismatched, print a warning but do NOT change it — the user's existing
   style takes priority.

2. **`\bibliography{}`**: If missing, add `\bibliography{references}` (or the
   detected `.bib` filename without extension) before `\end{document}`.

   For `biblatex` manuscripts: check for `\printbibliography` instead. If
   missing, add it. Also check for `\addbibresource{}` in the preamble — if
   missing, add it.

### Step 4.5 — Fill Citation Slots

If Phase 3a produced `slot_assignments`, fill each assigned slot in the output
`.tex` before free-placement insertion. The replacement text comes from the
`Type: slot` entries in `placement_plan.md` (the Phase 3b/3c output); the
`slot_assignments` array in `assignment.json` carries only the key assignment
(slot → cite keys), not the built cite command. Fill by exact string replacement,
using each slot entry's `**Anchor**` to locate the slot and its `**Replace slot
with**` text as the replacement. The mechanic depends on the slot `form`:

**Bare slot** (`form: bare`): replace the `% CITE: <hint>` comment with the cite
command (`\citep{}` / `\citet{}` / `\cite{}` per the package) at the anchor
point. The slot comment must not survive.
```latex
% Before:  ...reduces information asymmetry. % CITE: meta-analysis on Y
% After:   ...reduces information asymmetry \citep{smith2020meta, jones2019review}.
```

**Footnote-wrapped slot** (`form: footnote_two_line` or `footnote_one_line`):
the `% CITE: <hint>` anchor line locates the slot, and the enclosing
`\footnote{…}` shell is the replacement target — replace the **entire** shell
with the cite command. Author-date journals do not take citation footnotes, so
the footnote wrapper is discarded, not filled.
```latex
% Before:  ...shape financial development.\footnote{%
%          % CITE: study establishing X
%          }
% After:   ...shape financial development \citep{laporta1998law}.
```

**Unfilled slots** (listed in `unfilled_slots`): leave untouched — the
`% CITE:` comment stays in the manuscript to keep flagging the gap. If a slot's
anchor is not found, print a warning and treat it as unfilled.

**Never** modify `% RESULT:` comments or any other comment; only `% CITE:`
slots that have a `slot_assignments` entry are touched.

### Step 5 — Insert Citations (Two Modes)

Read `replan` from `run_config.json` to determine the insertion mode.

Each placement entry has a `**Type**` field: `parenthetical`, `prose`, or
`textual`. The insertion mechanic depends on the type.

#### Mode A: Deterministic insertion (`replan: false` — cached plan)

This mode uses exact anchor matching. No LLM judgment for placement.

1. Read `placement/placement_plan.md`. Parse each entry.
2. **Skip** all entries with `**Status**: inserted`.
3. For each entry with `**Status**: new`:

   **Type `parenthetical` (has "Insert after anchor"):**
   a. Find the **Anchor** string in the `.tex` using exact string matching.
   b. If found: insert the cite command immediately after the anchor.
   c. If not found: print "Anchor not found — skipping: [first 50 chars]..."
      Do NOT attempt fuzzy matching.

   **Type `prose` or `textual` (has "Replace anchor with"):**
   a. Find the **Anchor** string in the `.tex` using exact string matching.
   b. If found: replace the entire anchor string with the **Replace anchor
      with** text. This is a direct string substitution — the replacement
      includes the rewritten prose, cite commands, and punctuation.
   c. If not found: print "Anchor not found — skipping: [first 50 chars]..."
      Do NOT attempt fuzzy matching.

4. After each successful insertion/replacement, update the entry in
   `placement_plan.md`:
   - Change `**Status**` from `new` to `inserted`.
   - For Type `prose`/`textual`: also update the `**Anchor**` field to contain
     the replacement text. This way, if the plan is reused in a future run,
     the script can still locate the (now-replaced) text for context, and it
     knows the placement is already done.

#### Mode B: LLM-guided insertion (`replan: true` — fresh plan)

The LLM uses judgment if the anchor text doesn't match exactly.

1. Read the placement plan. All entries are `new`.
2. For each entry, find the insertion point using the anchor as a guide.
3. Apply the correct mechanic based on type:
   - `parenthetical`: insert cite command after the anchor.
   - `prose`/`textual`: replace the anchor with the replacement text.
4. Update status to `inserted` (and update anchor for prose/textual).

### Step 5.5 — Slot Closure Check (deterministic)

If the input manuscript contained `% CITE:` slots, verify slot closure on the
output `.tex` after all slot filling and citation insertion:

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
this check, which matches only `% CITE:`.

Include the reconciliation line in the final run report:
```
Slots: N found, M filled, K unfilled; grep remaining % CITE: = K (matches unfilled).
```

### Step 6 — Compile and Report

1. After all insertions, compile with the correct sequence:

   **For bibtex backend:**
   ```
   pdflatex [file]
   bibtex [file-without-ext]
   pdflatex [file]
   pdflatex [file]
   ```

   **For biber backend:**
   ```
   pdflatex [file]
   biber [file-without-ext]
   pdflatex [file]
   pdflatex [file]
   ```

   Three pdflatex passes are standard: first generates `.aux`, bibtex/biber
   processes references, second resolves citations, third resolves any
   remaining cross-references.

2. Check for errors. Common issues:
   - Missing `.bst` file → suggest user install the LaTeX package
   - Undefined citation warnings → check `.bib` key spelling
   - Missing `\bibdata` → ensure `\bibliography{}` is present
   - Unescaped `&` → fix with `\&`

3. Report the final state:
   - Number of citations inserted
   - Number of entries skipped (already `inserted`)
   - Number of anchors not found (skipped in Mode A)
   - Number of new `.bib` entries merged
   - Slots: [N] found, [M] filled, [K] unfilled (see Step 5.5 closure check)
   - Any compilation warnings
   - Path to the output `.tex` and `.pdf`

### Insertion Mechanics

**Type 1 — Simple parenthetical (insert after anchor):**
```latex
% Type: parenthetical
% Anchor: "consistent with the broader literature on board independence"
% Insert after anchor: \citep{gordon2006rise, adams2010role}
% Result:
...consistent with the broader literature on board independence
\citep{gordon2006rise, adams2010role}.
```

**Type 2 — Prose integration (replace anchor):**
```latex
% Type: prose
% Anchor: "The number of publicly listed firms has declined sharply across
%   developed markets, driven in part by the collapse of small-company
%   IPO activity."
% Replace anchor with: "The number of publicly listed firms has declined
%   sharply across developed markets \citep{doidge2017eclipse}, driven in
%   part by the collapse of small-company IPO activity
%   \citep{gao2013growth}."
% Result:
The number of publicly listed firms has declined sharply across developed
markets \citep{doidge2017eclipse}, driven in part by the collapse of
small-company IPO activity \citep{gao2013growth}.
```

**Type 3 — Textual citation (replace anchor):**
```latex
% Type: textual
% Anchor: "Prior work establishes that legal institutions and investor
%   protection shape financial development."
% Replace anchor with: "\citet{laporta1998law} establish that legal
%   institutions and investor protection shape financial development,
%   a finding extended to securities regulation by
%   \citet{laporta2006securities}."
% Result:
\citet{laporta1998law} establish that legal institutions and investor
protection shape financial development, a finding extended to securities
regulation by \citet{laporta2006securities}.
```

### Versioning Rules

| Original filename | Output filename |
|---|---|
| `Manuscript.tex` | `Manuscript_cited.tex` |
| `Manuscript_cited.tex` | `Manuscript_cited2.tex` |
| `Manuscript_cited2.tex` | `Manuscript_cited3.tex` |

### Constraints
- **Never modify the original `.tex`** — always work on the copy.
- In Mode A (deterministic), if an anchor is not found, skip it. Do not guess.
- **Slots**: fill only `% CITE:` slots that have a `slot_assignments` entry;
  leave unfilled slots and every `% RESULT:` comment untouched. Run the Step 5.5
  closure check before reporting done.
- If compilation fails persistently on a specific citation, comment it out with
  `% CITATION PLACEMENT FAILED: [reason]` and continue.

### Status Tracking

- `new` — not yet inserted. Phase 5 processes this entry.
- `inserted` — already inserted in a prior run. Phase 5 skips this entry.

After Phase 5 inserts a citation, it updates that entry from `new` to
`inserted` in `placement_plan.md`.
