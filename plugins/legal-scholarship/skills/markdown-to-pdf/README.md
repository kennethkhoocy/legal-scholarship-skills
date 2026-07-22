# markdown-to-pdf

Convert a GitHub-flavored Markdown (`.md`) file into a polished PDF with every
image preserved and scaled to fit the page. Pandoc's default LaTeX route breaks
on real-world Markdown — Unicode box-drawing characters in code blocks crash
pdflatex, wide tables overflow, remote images need manual downloading, and the
result looks nothing like the rendered Markdown you reviewed. This skill instead
renders the Markdown to HTML the way a browser would, then prints that HTML to
PDF, so the output matches what you see on GitHub. Use it whenever you want a PDF
deliverable of any Markdown document — a README, design doc, report, or notes —
especially one that contains images, tables, code blocks, or a linked table of
contents.

## When to use

- You ask to "save this markdown as a PDF", "convert README.md to pdf", "export
  the .md as a pdf", or "turn these notes/docs into a PDF".
- You want a PDF of any GitHub-flavored Markdown document, particularly one with
  hosted or local images and diagrams, GFM tables, fenced code blocks,
  blockquotes, or `#`-anchor table-of-contents links.
- The requirement is that all images must be preserved and scaled appropriately.

Do **not** use it for `.tex` → PDF (use a LaTeX toolchain) or for `.docx` work
(use a Word/LaTeX conversion skill).

## How it triggers in Claude Code

This skill auto-activates when a task matches the phrases and document types
above. In practice Claude Code runs the bundled `md2pdf.py` script on your
Markdown file and reports the verification result. You can also run the script
yourself (see below).

## The pipeline

1. **pandoc** renders the Markdown as `gfm` → standalone `html5`, executed from
   the Markdown file's own directory so relative image paths resolve, with the
   bundled print stylesheet applied. By default it embeds every resource
   (`--embed-resources`), fetching remote images and inlining them as data URIs
   so the HTML is self-contained.
2. **Headless Chrome** (or Chromium / Edge as a fallback) prints the HTML to PDF
   with `--no-pdf-header-footer` and a virtual-time budget so image loading
   finishes before printing.
3. **pypdf verification** counts the embedded raster images and compares that
   against the number of image references in the source, printing each image's
   page and pixel dimensions. A shortfall exits with a warning code.

The stylesheet constrains every image to the printable width, keeps a very tall
diagram on a single page, preserves aspect ratio, and avoids splitting an image
across a page break.

## Usage

Preferred (one command):

```
python scripts/md2pdf.py <input.md> [-o out.pdf]
```

Useful flags:

- `-o, --output` — output PDF path (defaults to alongside the input).
- `--css <file>` — override the print stylesheet (for letter size, landscape,
  and so on).
- `--browser <path>` — point at an explicit Chrome/Chromium/Edge binary.
- `--no-embed` — skip resource embedding; the browser fetches images at print
  time (useful when pandoc cannot reach a host the browser can).
- `--budget <ms>` — raise Chrome's virtual-time budget for many or slow remote
  images.
- `--keep-html` — keep the intermediate HTML beside the PDF.
- `--no-verify` — skip the pypdf image check.

## Requirements

- **pandoc** on `PATH` (https://pandoc.org/installing.html) — required.
- **A headless browser**: Chrome, Chromium, or Edge — required. The script
  searches `PATH` and then common install locations on Windows, Linux, and
  macOS; pass `--browser` if it cannot find one.
- **pypdf** — optional, used only for the image-verification step. Without it,
  conversion still runs and verification is skipped with a note.

## Folder contents

- `scripts/md2pdf.py` — the end-to-end converter (pandoc → headless browser →
  pypdf verification), with the flags listed above.
- `assets/print.css` — the GitHub-like print stylesheet (A4 with ~16 mm × 15 mm
  margins by default; image sizing, table borders and zebra striping, code-block
  styling, and cell wrapping). Copy or override it with `--css` for a different
  page size or layout.
- `SKILL.md` — the full skill guidance, including a manual pandoc-plus-browser
  equivalent of what the script automates.

## Platform notes and limitations

- The browser-locator table covers Windows, Linux, and macOS, so the script is
  cross-platform; only the default browser paths differ per OS.
- **Page-break trade-off:** keeping images whole means an image that does not
  fit the remaining space on a page moves to the next page, leaving white space
  behind. This is acceptable for reports; mention it when relevant.
- **SVG images** may render as vector art rather than raster XObjects, in which
  case the pypdf count under-reports and the warning is a false positive — check
  visually.
- **The same image referenced twice** may be embedded only once, so the
  "embedded ≥ referenced" check is a heuristic, not an exact equality test.
- **Locked output targets:** cloud-synced folders (Dropbox, OneDrive) or an open
  PDF viewer can prevent the browser from overwriting the target file while it
  still exits successfully. The script therefore prints to a temp directory and
  moves the result over the target with retries; if the target stays locked, it
  writes `<name>.new.pdf` and says so. Keeping the pypdf verification step on is
  what catches this class of failure.
