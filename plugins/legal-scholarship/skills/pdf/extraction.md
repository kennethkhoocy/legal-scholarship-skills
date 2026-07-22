# PDF Extraction

Detailed routing and recipes for reading text, tables, formulas, and layout from PDFs. SKILL.md runs `scripts/probe_pdf.py` first; this file documents what to do with the result.

## 1. Decision tree (full version)

```
Run scripts/probe_pdf.py. Then route by `classification`:

  encrypted              → halt, ask user for password, re-probe
  scanned                → scripts/lightonocr_run.py  (GPU, ~3 GB VRAM). See §5.
                           Fallback: dolphin (§5B).
  born_digital_footnotes → scripts/docling_extract.py  (footnotes + formula LaTeX).
                           See §4B. Then sanitize_math.py.
  born_digital_simple    → pypdf.extract_text()
  born_digital_formulas  → opendataloader-pdf --hybrid docling-fast --enrich-formula
                           (--restart-backend) → equations as LaTeX. See §4A.
  born_digital_tables    → pdfplumber.extract_tables()
  born_digital_complex   → opendataloader-pdf --hybrid docling-fast
  uncertain              → opendataloader first; escalate to lightonocr if output
                           has <100 chars/page OR high cid_ratio
```

`born_digital_formulas` is checked before `simple`/`tables`/`complex`: a math-dense
page sent to pypdf or pdfplumber loses its equations, so the probe routes it to the
LaTeX-capable backend regardless of how clean the surrounding layout looks.

Threshold reference (defined in `scripts/probe_pdf.py`):

| Threshold | Default | Triggers |
|---|---|---|
| `TUNE_TEXT_LAYER_SCANNED_MAX` | 50 chars/page | text_layer_coverage below this → scanned |
| `TUNE_CID_RATIO_SCANNED_MIN` | 0.3 | (cid:N) ratio above this → scanned |
| `TUNE_TEXT_LAYER_SIMPLE_MIN` | 500 chars/page | text_layer_coverage above this → born-digital candidate |
| `TUNE_COMPLEXITY_SIMPLE_MAX` | 0.1 | complexity below this → simple |
| `TUNE_TABLE_DENSITY_TABLES_MIN` | 0.3 | table density above this → tables |
| `TUNE_COMPLEXITY_COMPLEX_MIN` | 0.2 | complexity above this → complex |

All thresholds are marked `TUNE:` in the source and may need adjustment against real PDFs.

User override hints (always win over the probe):
- `"OCR"` / `"scanned"` → lightonocr (§5); `"use dolphin"` → dolphin (§5B)
- `"tables only"` / `"extract rows"` → pdfplumber + opendataloader
- `"formulas"` / `"equations"` / `"math"` / `"keep the LaTeX"` → §4A: opendataloader `--enrich-formula --restart-backend`, or lightonocr if scanned. Never pypdf/pdfplumber.
- `"fast"` / `"quick text"` → pypdf

## 2. pypdf — fastest path for clean born-digital text

### When
Probe says `born_digital_simple`. Or the user says "just give me the text" / "quick text dump".

### How
```python
from pypdf import PdfReader

reader = PdfReader("document.pdf")
text = "\n".join(page.extract_text() for page in reader.pages)
```

### Known limits
- Loses table structure (rows / columns collapsed into prose).
- Drops figure captions in some PDFs.
- Fails silently when fonts are subset-encoded — output looks like `(cid:1234)(cid:5678)...`.

### Verification
Sample the first 200 chars of the output. If length < 100 or `(cid:N)` patterns appear in more than 20% of the text, escalate to pdfplumber or opendataloader.

## 3. pdfplumber — born-digital with tables or coordinate-aware text

### When
Probe says `born_digital_tables`. Or the user mentions "tables", "extract rows", "spreadsheet from a PDF".

### Basic text extraction (layout-aware)
```python
import pdfplumber

with pdfplumber.open("document.pdf") as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        print(text)
```

### Table extraction
```python
import pdfplumber

with pdfplumber.open("document.pdf") as pdf:
    for i, page in enumerate(pdf.pages):
        for j, table in enumerate(page.extract_tables()):
            print(f"Page {i+1}, table {j+1}:")
            for row in table:
                print(row)
```

### Advanced table settings (tune for complex layouts)
```python
import pdfplumber

table_settings = {
    "vertical_strategy": "lines",      # 'lines' for ruled, 'text' for whitespace-delimited
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "intersection_tolerance": 15,
}
with pdfplumber.open("complex_table.pdf") as pdf:
    tables = pdf.pages[0].extract_tables(table_settings)
```

### Output to DataFrame / parquet (per user preference)
```python
import pdfplumber
import polars as pl

with pdfplumber.open("document.pdf") as pdf:
    all_rows = []
    for page in pdf.pages:
        for table in page.extract_tables():
            if not table:
                continue
            header, *rows = table
            df = pl.DataFrame({col: [r[i] for r in rows] for i, col in enumerate(header)})
            all_rows.append(df)

if all_rows:
    combined = pl.concat(all_rows, how="diagonal")
    combined.write_parquet("extracted_tables.parquet")
```

(Per the user's CLAUDE.md: prefer polars over pandas, prefer parquet over xlsx in analysis scripts.)

## 4. opendataloader-pdf — born-digital complex layout (hybrid Docling)

### When
Probe says `born_digital_complex`. Default for academic papers, multi-column layouts, mixed-content reports.

### Prerequisites
Java 11+ (system-installed). `pip install -U "opendataloader-pdf[hybrid]"` (already installed in this environment).

### Preferred — wrapper with progress bar + probe integration

Single line (runs in both PowerShell and Bash). The optional `--probe-output` reads the probe JSON and auto-derives `--force-ocr` / `--enrich-formula`:

```
python ~/.claude/skills/pdf/scripts/opendataloader_convert.py "<input.pdf>" -o "<output_dir>" --probe-output "<probe.json>"
```

The wrapper handles backend startup, health checks, and shows a tqdm progress bar. When `--probe-output` is given, the wrapper reads the probe JSON and auto-enables enrichments (`--force-ocr` if scanned, `--enrich-formula` if formula_density > 0.1).

### Manual method (alternative)

#### Step 1 — start the hybrid backend (if not already running)

Health check (works in both PowerShell and Bash because `curl.exe` is explicit):

```
curl.exe -s http://localhost:5002/health
```

After the call, check the exit code. In PowerShell: `$LASTEXITCODE` is `0` when the backend is healthy. In Bash: `$?` is `0`. A non-zero exit means the backend isn't running.

If not running, start it in the background:
```
opendataloader-pdf-hybrid --port 5002 --device auto
```
Wait until `/health` returns OK (poll every 3 s, up to 90 s).

#### Step 2 — convert

Single line:

```
opendataloader-pdf --hybrid docling-fast --format markdown -o "<output_dir>" "<input.pdf>"
```

### Default flags (overrides only when the user asks)

| Flag | Default | Notes |
|---|---|---|
| `--hybrid` | `docling-fast` | Selects the backend. Pass `off` (or omit) to disable hybrid. |
| `--hybrid-mode` | *(not passed — CLI default is `auto`)* | `auto` = dynamic triage; `full` = every page through backend (much slower). |
| `--format` | `markdown` | Can be `markdown,json`. |
| `-o` | same directory as input PDF | User may specify. |
| `--image-output` | `embedded` | Base64 images in markdown; use `external` for separate files. |

### Optional enrichments (require backend restart)

- OCR: `--force-ocr --ocr-lang "en"` (or user-specified languages)
- Formulas: `--enrich-formula`
- Image / chart descriptions: `--enrich-picture-description`

### Output
Markdown (default), JSON, or both (`--format markdown,json`). The Markdown file is the primary output to present to the user. Images are embedded as base64 unless `--image-output external` is set.

### Local-only mode (skip the backend)
```bash
opendataloader-pdf --format markdown -o "<output_dir>" "<input.pdf>"
```
Much faster (~0.05 s/page) but less accurate for complex layouts. Use only when the user explicitly asks.

### Python API
```python
import opendataloader_pdf

opendataloader_pdf.convert(
    input_path=["file.pdf"],
    output_dir="output/",
    format="markdown",
    hybrid="docling-fast",
)
```

## 4A. Math-heavy → LaTeX (the `born_digital_formulas` route)

When the probe returns `classification: born_digital_formulas` (or the user says
"formulas" / "equations" / "math" / "keep the LaTeX"), the goal is to emit each
equation as LaTeX rather than flatten it to broken inline text. Two backends can
do this; **pypdf and pdfplumber cannot** — never use them here.

### Primary — opendataloader-pdf with formula enrichment

`--enrich-formula` runs Docling's formula model, which renders detected equations
as LaTeX (`$$ … $$` display blocks, `\frac`, `\sum`, `\alpha`, `\begin{cases}`, …)
in the Markdown. The flag is consumed by the **hybrid backend**, so it only takes
effect when the backend is (re)started with it. The wrapper handles this when you
pass the probe JSON and force a fresh backend:

```
# 1. Probe and save the JSON (formula_density drives the auto-enabled flag)
python ~/.claude/skills/pdf/scripts/probe_pdf.py "<input.pdf>" > "<probe.json>"

# 2. Convert — the wrapper reads formula_density>0.1 and adds --enrich-formula;
#    --restart-backend guarantees the flag is applied even if a backend is running.
python ~/.claude/skills/pdf/scripts/opendataloader_convert.py \
  "<input.pdf>" -o "<output_dir>" --probe-output "<probe.json>" --restart-backend
```

`--restart-backend` matters: `--enrich-formula` is a backend-startup flag, so a
backend left running from an earlier run (or started without the flag) would
silently ignore it. With `--restart-backend` the wrapper terminates that backend
and starts a fresh one carrying the flag, then prints whether enrichment was
applied.

Manual equivalent (start the backend yourself with the flag):
```
opendataloader-pdf-hybrid --port 5002 --device auto --enrich-formula   # fresh backend
opendataloader-pdf --hybrid docling-fast --format markdown -o "<output_dir>" "<input.pdf>"
```

### Garbled figure-label text (auto-cleaned)

Born-digital vector figures (plots, phase diagrams) keep their axis and region
labels in the PDF text layer. The parser crops the figure to an image and writes
its caption, but it ALSO leaks those labels into the Markdown as a run of short,
disconnected, often mojibake fragments wedged between the image and the caption:

```
![image](...)
(d)
Full  Deterrence
{3 *          ← β*
=  0
~- · · ··· -  ← vector strokes misread as text
Prob. Informed (rr)   ← π
Figure 1: Equilibrium Characterization
```

`opendataloader_convert.py` strips these automatically after conversion (disable
with `--no-clean-fragments`). The cleaner removes fragment-dense, junk/noise-
heavy runs that sit next to a figure image or caption, while protecting LaTeX
(`$$…$$`, inline `$…$`), tables, headings, lists, images, captions, and prose.
The figure image and caption are kept — only the redundant leaked labels go.

Run it on any Markdown on its own (e.g. output from a previous conversion):
```
python ~/.claude/skills/pdf/scripts/clean_garbled_fragments.py \
  "<file.md>" --in-place      # or --dry-run to preview, -o OUT.md to copy
```

### KaTeX-safe math (auto)

The formula model occasionally emits the body of a multi-line aligned equation —
with alignment markers `&` and row breaks `\\` — but without the
`\begin{aligned} … \end{aligned}` wrapper. A KaTeX renderer then shows an inline
error such as `KaTeX parse error: Expected 'EOF', got '&'`. It also sometimes
splices prose or an undefined macro (`\intertext`, a mis-joined `\Deltad`) into a
block, or leaves a stray `\`.

`opendataloader_convert.py` repairs this automatically after conversion (disable
with `--no-sanitize-math`):

- a block with top-level `&` / `\\` is wrapped in `\begin{aligned} … \end{aligned}`
  so the equation renders, and
- the result is checked against the real KaTeX engine; a block that still fails
  (undefined macro, spliced prose, stray `\`) is suppressed — the `$$ … $$` is
  removed. Suppression happens only on a genuine parse error, never on a block
  KaTeX can render.

The KaTeX engine ships with the skill as a single vendored bundle
(`scripts/vendor/katex.min.js`), so validation works on every machine that has
Node — no install, and no `node_modules` placed in a synced config
folder. (A `PDF_SKILL_KATEX` env override and a machine-local npm cache are also
accepted as fallbacks.) When Node is absent, the step still performs the lossless
`aligned` wrap and removes only obvious debris, reporting heuristic mode. Run it standalone on any Markdown:

```
python ~/.claude/skills/pdf/scripts/sanitize_math.py "<file.md>" --in-place
# --dry-run to preview, --no-katex to force heuristic mode
```

### When equations still come out as plain text

The hybrid CLI's default `--hybrid-mode auto` triages only "complex" pages to the
Docling backend, so a page whose sole complex content is one inline-typeset display
equation can be judged simple — it never reaches the formula model and the equation
lands as flattened plain text even with `--enrich-formula` on. (Tell-tale: a 20-page
math paper converts in ~10 s and `verify_extraction.py` flags `flattened-equation`.)
`--hybrid-mode full` forces every page through the backend, but tested on a finance
paper it is a trade rather than a fix — it recovers simple display equations as
LaTeX while making multi-line/`cases` equations *worse* (`\intertext{…}` debris that
`sanitize_math.py` then suppresses), leaves dense tables merged, and is much slower.
So do not switch the default.

When the gate flags a flattened or broken equation, repair it the same way as a
mangled table (§4C): render the page region (`render_region.py`), read the equation
off the image, write it as a `$$ … $$` block (`\begin{cases}` for piecewise,
`\begin{aligned}` for multi-line), then validate against the real KaTeX engine —
`python scripts/sanitize_math.py "<out.md>" --in-place` flags anything KaTeX cannot
parse — and re-run `verify_extraction.py` until clean. That loop fixed the probit
`cases` equation a backend flag could not. For an all-image math/scan paper,
escalate straight to LightOnOCR instead (§5).

### Escalation — LightOnOCR

If the equations are **images** (formula_density may read low, or the LaTeX output
is sparse/garbled), or the probe says `scanned`, use LightOnOCR — it emits LaTeX
for formulas:
```
python ~/.claude/skills/pdf/scripts/lightonocr_run.py "<input.pdf>" -o "<out.md>"
```
It also accepts a single cropped equation image (png/jpg) directly. Cost is low
(GPU, ~3 GB VRAM, §5); dolphin `--mode element --element_type formula` remains the
fallback (§5B).

### Verify the LaTeX is actually there

After conversion, confirm equations came out as LaTeX, not flattened text:
```bash
grep -cE '\$\$|\\frac|\\sum|\\int|\\alpha|\\begin\{' "<output_dir>/<stem>.md"
```
A high `formula_density` with **zero** LaTeX hits means `--enrich-formula` did not
apply — re-run with `--restart-backend`, or escalate to LightOnOCR (§5).

## 4B. Footnotes + academic papers → Docling-direct

When the probe returns `born_digital_footnotes` (or the user says "keep the
footnotes", "academic paper", "law review", "journal article"), use the
Docling-direct backend. opendataloader-pdf discards Docling's footnote labels and
jumbles the footnote text into the body; calling Docling directly preserves both
the footnote definitions and the in-body reference markers, so they can be
reconstructed as proper Markdown footnotes — and Docling also emits formula
LaTeX, so this one path covers footnotes *and* equations.

```
python ~/.claude/skills/pdf/scripts/docling_extract.py \
  "<input.pdf>" -o "<output.md>" [--pages A-B] [--no-formula]
# then make the math KaTeX-safe:
python ~/.claude/skills/pdf/scripts/sanitize_math.py "<output.md>" --in-place
```

What it produces:
- Footnotes are **inlined at their reference point** as pandoc inline footnotes:
  `… the IPO documents.^[See Atkins (2018) and Graf (2018).] After …`. The note's
  start (`^[`) and end (`]`) are visible in the raw Markdown in any viewer, and
  pandoc turns them into inline `\footnote{}`. Brackets inside the note text are
  escaped so they don't terminate the note. Symbol notes (`∗ * † ‡ §`) are each
  inlined at their in-body marker — not only the first acknowledgment star —
  while skipping Markdown bullets/emphasis and `§`-statute references; a symbol
  note with no locatable marker goes to `## Endnotes` with its symbol preserved.
  Long notes Docling split into fragments are merged back into one entry
  (sequence-aware, so a citation volume like `93 YALE L.J.` stays inside the
  note, not a phantom footnote 93). A page-range extraction beginning
  mid-document keeps its first footnote's number even when it starts above 20.
- Markers are located in two passes (greedy in-order + recovery of unique
  out-of-order markers) with a context filter that excludes cross-references
  ("Section 4", "see note 12"), years, quantities, dates, and section-number
  headings. The run reports `markers_linked` and `endnotes`.
- A footnote whose marker cannot be found in the text — e.g. absorbed into an
  equation, the common case in math-dense sections — is emitted under
  `## Endnotes` as `**[n]** text` (by original number), since there is no
  reference point to inline it at. This also survives pandoc (a bare `[^n]:`
  with no reference would be dropped), so no footnote content is lost on the
  `.md → .tex` bridge.
- Equations are emitted as `$$…$$` LaTeX. Figures Docling detects as pictures are
  embedded as base64 (`--image-output external|none` to change); vector-line
  figures (e.g. drawn phase diagrams, Stata/matplotlib charts, vector maps) are
  not detected as pictures and so are not captured — recover them with
  `scripts/extract_figures.py` (§4C). Docling keeps figure text out of the body,
  so the §"Garbled figure-label text" cleanup is not needed on this path.

Pass `--no-formula` for non-math papers (skips the formula model — faster). For
born-digital this runs without a GPU in seconds-to-minutes; the formula model is
the slow part on math-heavy documents.

### → LaTeX for a `.tex`-consuming skill

The Markdown is pandoc-ready: inline footnotes (`^[…]`) become `\footnote{}`, `$$…$$`
stays LaTeX math, headings become `\section{}`. Convert with:
```
pandoc "<output.md>" -f markdown -t latex -s --extract-media=<dir> -o "<output.tex>"
```
Drop `-s` if the downstream skill wants a body fragment rather than a standalone
document. Because unlinkable footnotes are emitted as endnotes (not bare `[^n]:`
defs), pandoc no longer drops them — nothing is lost in conversion.

## 4C. Recovering figures and tables Docling drops or mangles

The Docling-direct path (§4B) is strong on text, footnotes, and formulas but has
two blind spots on figure-rich, dense-table papers (typical of finance/economics
journal articles). Both are recoverable without re-running the whole extraction.

### Vector figures it never captures → `scripts/extract_figures.py`

§4B notes that vector figures (charts, maps, ownership-tree diagrams drawn as
graphics rather than embedded rasters) are not detected as pictures. To recover
them and link them back into the Markdown:

```
python ~/.claude/skills/pdf/scripts/extract_figures.py \
  "<input.pdf>" --link-md "<extracted.md>"
```

It renders every figure page (a page whose text has a `Figure <label>.` caption
AND carries graphics) to a cropped PNG under `<stem>_images/` — caption-anchored
crop for vector figures, image-bbox crop for raster ones — then with `--link-md`
inserts each image above its caption and drops the **duplicate caption lines**
Docling emits (it tends to print every caption twice). Verify: each figure label
has exactly one image link + one caption, and 2-3 crops match the page.

### Dense / sideways tables it collapses → render the region and rewrite it

Docling's table model fails two ways on dense tables:
- multi-panel regression tables → cells **spill vertically**, one per line
  (`Panel A / Excl. Top 5% / (2) / 0.0544 ** / (0.0193) / Yes / 0.09 / …`);
- long or sideways data tables → **adjacent rows merge** (`France Germany` in one
  country cell, values doubled like `270 48`, `1.359 ∗∗∗ (0.310) 0.572`).

(Skip this whole loop in **light mode** — user said "light mode" / "no hand
repair". Report the gate's flagged lines as known defects and ship; see SKILL.md
§Verification.)

When `verify_extraction.py` flags `merged-table-row`, do **not** try to coax the
table model and do **not** reach for a positional re-binning script. A positional
extractor needs a hand-tuned bbox and column count for every table, only handles
numeric grids, and still loses spanning headers and lone standard-error rows — it
trades one fiddly failure for another. The reliable, general repair is to look at
the original and rewrite the block:

```
python ~/.claude/skills/pdf/scripts/render_region.py \
  "<pdf>" --page N [--bbox x0,y0,x1,y1]
```

Get the page number from the gate's caption/line context; render the whole page,
or pass `--bbox x0,y0,x1,y1` (PDF points, top-left origin — the coordinates
`pdfplumber`'s `extract_words()` reports) to crop to just the table. Open the PNG,
read the table, and rewrite that block of the Markdown as clean pipe rows — one
data row per line, standard errors on their own line, significance stars as
`<sup>**</sup>`. This one method handles every table shape: numeric regression
grids, multi-panel tables, and **definitions tables** (Variable | Description with
prose + math per cell), where you write each formula as inline `$…$` LaTeX. A
positional script cannot do that last case at all.

Then re-run `verify_extraction.py` — it should report clean. The same render-and-
rewrite loop fixes a broken or flattened equation (§4A): render the region, read
it, write the `$$…$$` / `\begin{cases}` LaTeX, validate with `sanitize_math.py`.

(Worked example: a regression table whose `Market Cap` / `R-squared` rows Docling
merged into one cell, and an 85-country panel whose last ~67 rows it collapsed —
both rebuilt correctly by rendering the region and transcribing it, no per-table
tuning.)

## 5. LightOnOCR-2-1B — vision-LM OCR (PRIMARY for scans)

### When
Probe says `scanned` (`recommended_backend: lightonocr`). Or extracted output from cheaper backends verifies poorly. Or the user says "OCR this" / "photographed document" / "scanned".

### Cost
- GPU REQUIRED — the wrapper aborts (exit 2) if CUDA is unavailable or the model lands off-GPU; it never falls back to CPU. It logs `model device: cuda:0` + torch's VRAM allocation as proof.
- ~3 GB VRAM (1B params, bf16); the wrapper aborts if less than 4 GB is free.
- First run auto-downloads ~2.5 GB of weights from Hugging Face (cached under `~/.cache/huggingface`).
- Fast: a page takes on the order of a second or two on the RTX 5080.

### Run
```bash
python ~/.claude/skills/pdf/scripts/lightonocr_run.py "<input.pdf>" -o "<output.md>" [--pages 1-5]
```
- Input may also be a single image (`.png`/`.jpg` — a photographed page, a cropped table or equation).
- Output is one Markdown file, math emitted as LaTeX. Then run `sanitize_math.py --in-place` and `verify_extraction.py` as usual.
- The wrapper re-execs itself under the venv at `~/LightOnOCR/venv` (override with the `LIGHTONOCR_DIR` env var), pre-checks free VRAM, and prints the `VRAM released: X MB remaining` marker at the end — same cleanup ritual as dolphin (§5B).

### Fallback
Venv missing, or output empty/garbled → dolphin (§5B). Dolphin is also the path for layout-only analysis (bounding boxes + reading order), which LightOnOCR does not do.

## 5B. dolphin v2 — vision-LM OCR (FALLBACK)

### When
LightOnOCR is unavailable or its output verifies poorly. Or the user explicitly says "use dolphin". Or you need element/layout modes (cropped-element decoding with `--element_type`, layout-only bounding boxes) — dolphin-only capabilities.

### Cost reminder (state every time before running)
- 7.5 GB VRAM (model uses ~7.1 GB on disk).
- ~20–30 s model load on first run.
- Sequential per-page processing.
- For a 50-page scan, budget 5–10 minutes.

### Setup (Dolphin OCR path; override the install dir with the `DOLPHIN_DIR` env var)
- Install dir: `~/Dolphin/`
- Venv: `~/Dolphin/dolphin-env/Scripts/activate`
- Model weights: `~/Dolphin/hf_model/` (7.1 GB, local)
- GPU required (script refuses CPU at startup).

### Three modes — use the wrapper, not the raw demo scripts

#### Page-level (default — for whole documents)
```bash
python ~/.claude/skills/pdf/scripts/dolphin_run.py \
  --mode page \
  --input <file_or_directory> \
  --save_dir <output_directory> \
  --max_batch_size 4
```

#### Element-level (for cropped element images — a table screenshot, a formula photo)
```bash
python ~/.claude/skills/pdf/scripts/dolphin_run.py \
  --mode element \
  --input <image_file_or_directory> \
  --save_dir <output_directory> \
  --element_type <table|formula|text|code>
```

#### Layout-only (bounding boxes + reading order, no element decoding)
```bash
python ~/.claude/skills/pdf/scripts/dolphin_run.py \
  --mode layout \
  --input <file_or_directory> \
  --save_dir <output_directory>
```

### What the wrapper does for you
1. Activates the Dolphin venv (`~/Dolphin/dolphin-env/`).
2. `cd`s into `~/Dolphin/`.
3. Runs `nvidia-smi --query-gpu=memory.free`. If less than 8 GB free, refuses to start and prints three options (wait, use opendataloader, reduce `--max_batch_size`).
4. Dispatches to `demo_page.py`, `demo_element.py`, or `demo_layout.py`.
5. After the run, verifies the `VRAM released: X MB remaining` marker is in the output. Warns if missing.

### Output structure (under `--save_dir`)
```
output_json/         # structured JSON (bbox, label, reading_order, tags)
markdown/            # primary Markdown output
markdown/figures/    # cropped figures
```

Read the Markdown file(s) from `markdown/` first — it's the primary output. Use the JSON for richer structured metadata.

### VRAM cleanup (CRITICAL)

The wrapper verifies the `VRAM released: X MB remaining` line. If it's missing or VRAM stays high after a run, find the orphaned OCR process and kill ONLY that PID — never blanket-kill python (other GPU jobs and pipelines may be running):

**PowerShell variant** (Windows native):
```powershell
nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader
Get-CimInstance Win32_Process -Filter "ProcessId = <pid>" | Select-Object CommandLine  # confirm it's the OCR worker
Stop-Process -Id <pid> -Force
nvidia-smi --query-gpu=memory.used,memory.free --format=csv
```

**Bash variant** (Git Bash / WSL / Linux):
```bash
nvidia-smi --query-compute-apps=pid,name --format=csv,noheader
ps -p <pid> -o args=   # confirm it's the OCR worker, not another GPU job
kill -9 <pid>
nvidia-smi --query-gpu=memory.used,memory.free --format=csv
```

If writing a custom Python script that uses the `DOLPHIN` class directly, always clean up at the end:

```python
import gc, torch
del model, processor
gc.collect()
torch.cuda.empty_cache()
```

Never leave the model loaded in VRAM between separate tasks. Load → process → clean up → done.

### Batch processing
Pass a directory as `--input`. The wrapper iterates over all supported files (JPG, JPEG, PNG, PDF).

### Tips
- Auto-detects distorted / photographed documents (via bbox overlap analysis) and falls back to full-page parsing if layout detection fails.
- Large PDFs take time because each page is rasterized and processed sequentially. State the budget to the user.
- If CUDA OOM, reduce `--max_batch_size` to 2 or 1.

## 6. Escalation — when one backend isn't enough

| Symptom | Action |
|---|---|
| pypdf returned `(cid:N)` garbage | Escalate to pdfplumber. |
| pdfplumber tables came back with empty cells | Escalate to opendataloader hybrid. |
| opendataloader returned thin text on a born-digital probe | Check if PDF is actually scanned; if yes, escalate to lightonocr. |
| opendataloader backend fails to start | Fall back to pdfplumber + pytesseract. Warn the user about reduced quality. |
| LightOnOCR venv missing / output garbled | Fall back to dolphin (§5B). |
| Dolphin OOM | Reduce `--max_batch_size` to 2 or 1; retry. |
| Both GPU OCR backends unavailable | Fall back to opendataloader with `--force-ocr` + pytesseract for any remaining gaps. |

## 7. OCR fallback (no GPU available)

When both GPU OCR backends are unavailable or the user explicitly opts out of GPU work, use pytesseract + pdf2image:

```python
# pip install pytesseract pdf2image
import pytesseract
from pdf2image import convert_from_path

images = convert_from_path("scanned.pdf")
text = ""
for i, image in enumerate(images):
    text += f"Page {i+1}:\n"
    text += pytesseract.image_to_string(image)
    text += "\n\n"
print(text)
```

Lower quality than the GPU backends (especially for tables and formulas), but works without GPU.

## 8. Verification checklist (after EVERY extraction)

Run the executable gate before the manual checklist — it turns the silent failures below into line-numbered flags:

```
python ~/.claude/skills/pdf/scripts/verify_extraction.py "<out.md>" --probe "<probe.json>"
```

`verify_extraction.py` detects the three things that look plausible but are wrong on born-digital academic papers, and that no backend reliably gets right:
- **merged/spilled table rows** — Docling's table model collapses dense regression tables, putting two rows' values in one cell (`1.359 ∗∗∗ (0.310) 0.572`, `1.47m Yes Yes`). Fix: render the table region (`render_region.py`) and rewrite that block from the image (§4C). This is the single most common silent failure on finance/econ tables.
- **broken/flattened equations** — empty `$$` blocks, `\intertext` debris from a defeated multi-line/`cases` equation, or (with `--probe`) high `formula_density` but display math left as plain text. Fix: hand-rebuild the equation (`\begin{cases}`) or escalate to lightonocr.
- **stray private-use glyphs** — leaked font codepoints; whole-PUA lines are now auto-stripped by `clean_garbled_fragments.py`, so a remaining inline one marks a flattened equation to hand-fix.

Exit 1 means fix-before-ship. A clean gate plus the manual items below = done.

- [ ] Output length is proportional to page count (a 50-page PDF shouldn't return 200 characters).
- [ ] No high `(cid:N)` ratio in the result.
- [ ] Tables, if expected, are preserved as structure (rows / columns), not flattened to prose.
- [ ] Special characters (Greek letters, math symbols) extracted correctly (not replaced with `?` or `□`).
- [ ] For `born_digital_formulas`: equations are present as LaTeX (`$$…$$`, `\frac`, `\sum`, `\alpha`, …), not flattened prose. If `formula_density` was high but no LaTeX appears, `--enrich-formula` did not apply — re-run with `--restart-backend` or escalate to lightonocr (see §4A).
- [ ] For lightonocr / dolphin: `VRAM released: X MB remaining` line present in the wrapper's stdout.
- [ ] For opendataloader hybrid: backend was healthy (`curl http://localhost:5002/health` returns OK).
- [ ] Output file exists at the expected path and is non-empty.
