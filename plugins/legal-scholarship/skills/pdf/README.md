# PDF Skill

One auto-triggered entry point for all PDF work: reading/extraction, OCR, and manipulation. The skill probes each PDF first, then routes to the cheapest backend that can do the job — heavy paths (GPU vision-LM) are a last resort.

## Installation

Clone the containing repository, then copy this skill into your host's skills
directory. The installed folder **must** be named `pdf` so that `SKILL.md` is at
the expected top level:

```bash
git clone https://github.com/kennethkhoocy/legal-scholarship-skills

# Claude Code:
mkdir -p ~/.claude/skills
cp -R legal-scholarship-skills/plugins/legal-scholarship/skills/pdf ~/.claude/skills/pdf

# Codex:
mkdir -p ~/.agents/skills
cp -R legal-scholarship-skills/plugins/legal-scholarship/skills/pdf ~/.agents/skills/pdf
```

Install the Python dependencies:

```bash
pip install pypdf pdfplumber opendataloader-pdf docling reportlab
```

Optional extras:

- **Math validation** — needs Node on `PATH`; the KaTeX bundle is already vendored at `scripts/vendor/`, so no `npm install`. Without Node, `sanitize_math.py` falls back to a lossless heuristic mode.
- **OCR (LightOnOCR-2-1B, primary)** — needs a CUDA GPU with ~3 GB free VRAM and a dedicated venv at `~/LightOnOCR/venv` (override with `LIGHTONOCR_DIR`), because it requires transformers v5 while Docling pins v4:

  ```bash
  python -m venv ~/LightOnOCR/venv
  ~/LightOnOCR/venv/Scripts/python -m pip install torch --index-url https://download.pytorch.org/whl/cu130
  ~/LightOnOCR/venv/Scripts/python -m pip install transformers pillow pypdfium2 accelerate
  ```

  (`Scripts` → `bin` on Linux/macOS.) Model weights (~2.5 GB) auto-download from Hugging Face on first run. Only the scanned/photographed path uses it; everything else is CPU. If the venv is missing, `lightonocr_run.py` aborts with these setup instructions.
- **OCR fallback (dolphin v2)** — fully optional. Install Dolphin separately at `~/Dolphin` (or point `DOLPHIN_DIR` at it) plus ~7.5 GB free VRAM. Used only when LightOnOCR is unavailable or for its element/layout modes. Without either GPU backend, the CPU fallback is opendataloader-pdf or pytesseract + pdf2image — the rest of the skill is unaffected.

Set the skill root for the host you use, then verify the install:

```bash
PDF_SKILL_ROOT=~/.claude/skills/pdf  # Claude Code
# PDF_SKILL_ROOT=~/.agents/skills/pdf  # Codex
python -m pytest "$PDF_SKILL_ROOT/tests/" -q   # expect: 216 passed
```

Claude Code and Codex discover the skill on the next launch or new session — no
manifest edit is needed. It auto-activates for PDF work; explicit invocation is
`/pdf` in Claude Code or `$pdf` in Codex.

## How it works

1. **Probe** (`scripts/probe_pdf.py`, ~1s, no GPU) classifies the PDF and recommends a backend.
2. **Route** by task and classification.
3. **Verify** (`scripts/verify_extraction.py`) gates every extraction.

### Quick start

```bash
# 1. Probe (always first) — returns JSON: classification, densities, recommended_backend
python "$PDF_SKILL_ROOT/scripts/probe_pdf.py" input.pdf > probe.json

# 2. Route on the result. Example: an academic paper (born_digital_footnotes)
python "$PDF_SKILL_ROOT/scripts/docling_extract.py" input.pdf -o out.md
python "$PDF_SKILL_ROOT/scripts/sanitize_math.py" out.md --in-place

# 3. Gate the output before trusting it
python "$PDF_SKILL_ROOT/scripts/verify_extraction.py" out.md --probe probe.json
```

### Routing table

| You want to… | Backend | When |
|---|---|---|
| Quick text dump | pypdf | Born-digital, no tables |
| Tables | pdfplumber | Table-heavy born-digital |
| Academic paper (footnotes/math) | `scripts/docling_extract.py` | Footnotes inlined, formulas as LaTeX |
| Markdown with structure | opendataloader-pdf hybrid | Complex layouts |
| Math-heavy (equations as LaTeX) | opendataloader `--enrich-formula` | Born-digital formulas |
| Scanned / photographed / formula images | `scripts/lightonocr_run.py` | GPU, ~3 GB VRAM, LaTeX-aware; dolphin v2 fallback |
| Reviewer comments / highlights / sticky notes | `scripts/extract_annotations.py` | Annotated manuscripts — reads the PDF annotation layer the extraction backends skip |
| Merge / split / rotate / watermark / encrypt | pypdf or qpdf | Manipulation |
| Create from scratch | reportlab | Generation |

User hints override the probe: `"OCR this"` (→ lightonocr), `"use dolphin"` (→ dolphin fallback), `"tables only"`, `"keep the footnotes"` / `"academic paper"`, `"formulas"` / `"keep the LaTeX"`, `"fast"`, `"light mode"` / `"no hand repair"` (skip the hand-repair loop; report-only gate).

### Probe classifications

`probe_pdf.py` returns one of: `encrypted` (halt, ask for password), `scanned` (→ lightonocr), `born_digital_footnotes` (→ docling, footnote+formula aware), `born_digital_simple` (→ pypdf), `born_digital_formulas` (→ opendataloader `--enrich-formula`), `born_digital_tables` (→ pdfplumber), `born_digital_complex` (→ opendataloader hybrid), `uncertain` (→ opendataloader, escalate to lightonocr), `error`. It also reports `formula_density` and `footnote_density` (the signals behind the formula/footnote routing) and a one-line `reasoning`.

### Verification gate

`verify_extraction.py` catches the three silent failures that look plausible but are wrong on born-digital papers: dense table rows **merged** into one cell, equations **flattened or garbled** (including `\intertext` debris), and stray private-use glyphs — each flagged with a line number and a fix pointer. Exit 1 = fix before shipping. The repair for a flagged table or equation: render that page region (`render_region.py`), read it, and rewrite the block from the image, then re-run the gate until clean.

## Files

- `SKILL.md` — full routing spec and decision trees (the authoritative reference).
- `extraction.md` / `manipulation.md` — per-task playbooks.
- `scripts/` — see below.
- `tests/` — pytest suite for the scripts (`python -m pytest tests/ -q`).

### Scripts

| Script | Role |
|---|---|
| `probe_pdf.py` | Classifier — run first. |
| `docling_extract.py` | Academic-paper extraction: footnotes inlined as pandoc `^[…]` notes, unlocatable notes routed to `## Endnotes`, formulas as LaTeX. |
| `opendataloader_convert.py` | opendataloader-pdf wrapper with progress bar + probe integration; post-cleans Markdown. |
| `sanitize_math.py` | Makes leaked/garbled math KaTeX-safe (wraps alignment, suppresses unrenderable blocks). |
| `katex_validate.js` | Node helper validating LaTeX against the real KaTeX engine (oracle behind `sanitize_math.py`). |
| `clean_garbled_fragments.py` | Strips leaked vector-figure label fragments and private-use-glyph lines. |
| `extract_figures.py` | Recovers vector/raster figures Docling drops; `--link-md` inserts them at captions. |
| `render_region.py` | Renders a page or `--bbox` region to PNG so a flagged table/equation can be reread and rewritten. |
| `verify_extraction.py` | Post-extraction quality gate — run last. |
| `extract_annotations.py` | Extracts reviewer comments, highlights, and sticky notes from the PDF annotation layer; one Markdown entry per annotation with page, author, comment text, marked span, and the surrounding paragraph. |
| `lightonocr_run.py` | Primary OCR: scanned PDF/image → Markdown (LaTeX-aware) via LightOnOCR-2-1B; venv re-exec, VRAM pre-check + release marker. |
| `dolphin_run.py` | Fallback OCR: wrapper for the Dolphin demo scripts (activates venv, VRAM pre-check + release check); element/layout modes. |

## Requirements & configuration

- **Python** — pypdf, pdfplumber, opendataloader-pdf, Docling, reportlab.
- **Node** — only for KaTeX math validation; the bundle is vendored at `scripts/vendor/katex.min.js`, so no `npm install` is needed. Override its location with the `PDF_SKILL_KATEX` env var if desired. When Node is absent, `sanitize_math.py` falls back to a lossless heuristic mode.
- **GPU** — only for OCR: ~3 GB VRAM for LightOnOCR (primary), ~7.5 GB for the dolphin fallback; everything else is CPU.
- **`LIGHTONOCR_DIR`** env var — points at the LightOnOCR install (contains `venv/`). Defaults to `~/LightOnOCR`.
- **`DOLPHIN_DIR`** env var — points at the Dolphin install (demo scripts, venv, weights). Defaults to `~/Dolphin`.

## Related skills

- `markdown-to-pdf` — for going `.md` → PDF.
- `latex-from-mixed-sources` — building a `.tex` manuscript from extracted text.
- `manuscript-editing-template-latex` — docx ↔ LaTeX round-tripping.

## License

MIT (repository license). All components in this distribution are user-authored. PDF form filling is not included; Anthropic's own document-skills plugin provides a form-filling toolchain.
