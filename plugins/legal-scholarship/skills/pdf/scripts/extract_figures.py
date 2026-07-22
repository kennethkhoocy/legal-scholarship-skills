"""Recover figures that Docling / opendataloader silently drop, and link them
into an extracted Markdown file.

Why this exists: the Docling-direct path (docling_extract.py, §4B) only captures
figures Docling detects as *pictures* — embedded raster images. Born-digital
academic papers routinely draw their figures (Stata/matplotlib charts, vector
world-maps, ownership-tree diagrams) as vector graphics, which Docling never
flags, so they vanish from the Markdown (it keeps only the caption text). §4B
notes this limitation but provides no recovery; this script is that recovery.

It finds every figure page (a page whose text has a "Figure <label>." caption
line AND carries graphics), crops the figure region, and renders it to a PNG:
  * vector figures  -> caption-anchored crop: from below any running header down
    to the top of the caption line, full text width (captures the chart and its
    in-figure axis labels/title, excludes the header and the caption below).
  * raster figures  -> crop to the union of the embedded image bboxes.

With --link-md, it also inserts an image link above each caption in the .md and
drops the duplicate caption lines Docling tends to emit (every caption twice).

Usage:
    python extract_figures.py <input.pdf> [-o <images_dir>] [--dpi 3]
        [--link-md <extracted.md>] [--label-regex "Figures?\\s+(...)"]

Output: <images_dir>/fig_<label>.png + <images_dir>/manifest.tsv
Defaults: images_dir = "<pdf_stem>_images" next to the PDF; dpi multiplier 3.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import fitz  # PyMuPDF

# A caption line: starts with "Figure"/"Fig." + a label + a period. The label
# group is permissive (numeric "7", appendix "IA-A.12", "S3", "A.4", ...).
DEFAULT_LABEL = r"^\s*Figures?\s+((?:[A-Z]{1,3}-)?[A-Z]?\.?\d+(?:\.\d+)?)\.(?=\s|$)"
HEADER_RE = re.compile(r"Journal|Proceedings|^\s*\d{1,4}\s*$|©|doi:|Downloaded from", re.I)


def caption_lines(page, label_re):
    """[(label, y0, full_text)] for caption lines + running-header bottom y."""
    caps, header_bottom = [], None
    for blk in page.get_text("dict").get("blocks", []):
        for ln in blk.get("lines", []):
            txt = "".join(sp["text"] for sp in ln.get("spans", []))
            y0, y1 = ln["bbox"][1], ln["bbox"][3]
            m = label_re.match(txt)
            if m:
                caps.append((m.group(1), y0, txt.strip()))
            if y0 < page.rect.height * 0.12 and HEADER_RE.search(txt.strip()):
                header_bottom = max(header_bottom or 0, y1)
    return caps, header_bottom


def image_bbox(page):
    rects = [r for xref, *_ in page.get_images(full=True)
             for r in page.get_image_rects(xref)]
    if not rects:
        return None
    return fitz.Rect(min(r.x0 for r in rects), min(r.y0 for r in rects),
                     max(r.x1 for r in rects), max(r.y1 for r in rects))


def crop_for(page, caps, header_bottom):
    pr = page.rect
    cap_y0 = caps[0][1]
    has_img, has_vec = bool(page.get_images()), len(page.get_drawings()) > 20
    if has_img and not has_vec:
        bb = image_bbox(page)
        return fitz.Rect(bb.x0 - 6, bb.y0 - 6, bb.x1 + 6, bb.y1 + 6) if bb else None
    top = (header_bottom + 4) if header_bottom else pr.height * 0.06
    if cap_y0 - top >= pr.height * 0.18:            # caption sits below the figure
        return fitz.Rect(pr.width * 0.05, top, pr.width * 0.95, cap_y0 - 4)
    draws = [p["rect"] for p in page.get_drawings() if p.get("rect")]
    if draws:                                       # caption above/beside: use gfx bbox
        return fitz.Rect(pr.width * 0.06, min(r.y0 for r in draws) - 6,
                         pr.width * 0.94, max(r.y1 for r in draws) + 6)
    return None


def extract(pdf_path: Path, images_dir: Path, dpi: float, label_re):
    doc = fitz.open(str(pdf_path))
    images_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for i, pg in enumerate(doc):
        caps, hb = caption_lines(pg, label_re)
        if not caps or not (pg.get_images() or len(pg.get_drawings()) > 20):
            continue
        crop = crop_for(pg, caps, hb)
        if crop is None or crop.is_empty or crop.width < 40 or crop.height < 40:
            continue
        label = caps[0][0]
        out = images_dir / f"fig_{label}.png"
        pg.get_pixmap(matrix=fitz.Matrix(dpi, dpi), clip=crop).save(str(out))
        manifest.append((label, i + 1, out.name, caps[0][2][:90]))
    (images_dir / "manifest.tsv").write_text(
        "\n".join(f"{l}\t{p}\t{f}\t{c}" for l, p, f, c in manifest), encoding="utf-8")
    return manifest


def link_into_md(md_path: Path, images_dir: Path, manifest, label_re):
    """Insert an image link above the first caption of each figure and drop the
    duplicate caption lines Docling emits."""
    pngs = {l: f for l, _, f, _ in manifest}
    rel = images_dir.name
    lines = md_path.read_text(encoding="utf-8").splitlines()
    out, inserted, last_cap, dups = [], set(), None, 0
    for ln in lines:
        m = label_re.match(ln)
        if m:
            if ln == last_cap:                      # exact-duplicate caption
                dups += 1
                continue
            lab = m.group(1)
            if lab in pngs and lab not in inserted:
                out += [f"![Figure {lab}](<{rel}/{pngs[lab]}>)", ""]
                inserted.add(lab)
            out.append(ln)
            last_cap = ln
            continue
        out.append(ln)
        if ln.strip():
            last_cap = None
    md_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return len(inserted), dups


def main():
    ap = argparse.ArgumentParser(description="Recover vector/raster figures Docling drops.")
    ap.add_argument("input_path")
    ap.add_argument("-o", "--images-dir", default=None)
    ap.add_argument("--dpi", type=float, default=3.0, help="render scale multiplier")
    ap.add_argument("--link-md", default=None, help="insert links + dedupe captions in this .md")
    ap.add_argument("--label-regex", default=DEFAULT_LABEL)
    args = ap.parse_args()

    pdf = Path(args.input_path)
    images_dir = Path(args.images_dir) if args.images_dir else pdf.with_name(f"{pdf.stem}_images")
    label_re = re.compile(args.label_regex)

    manifest = extract(pdf, images_dir, args.dpi, label_re)
    print(f"[figures] rendered {len(manifest)} -> {images_dir.name}/")
    for l, p, f, c in manifest:
        print(f"  Figure {l:<10} p{p:<4} {f}")
    if args.link_md:
        n, d = link_into_md(Path(args.link_md), images_dir, manifest, label_re)
        print(f"[figures] linked {n} into {Path(args.link_md).name}; dropped {d} duplicate captions")


if __name__ == "__main__":
    main()
