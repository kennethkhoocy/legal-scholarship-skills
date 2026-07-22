"""Render a PDF page (or a region of it) to a PNG so it can be read back and rewritten.

The reliable, general repair for a table or equation the layout parser mangled is
not a positional heuristic that needs per-document tuning — it is to look at the
original. Render the region, read it, and rewrite the Markdown / LaTeX from what
you see. One approach covers numeric regression grids, prose+math definitions
tables, and multi-line/`cases` equations, with no parameters to fit. This is what
`verify_extraction.py` points you at when it flags a merged table or a broken
equation, and it is what produced the correct tables in the worked example.

Usage:
    python render_region.py <pdf> --page N [--bbox x0,y0,x1,y1] [-o out.png] [--dpi 300]

`--bbox` is in PDF points with a top-left origin (the same coordinates
`pdfplumber`'s `extract_words()` reports as `x0`/`top`/`x1`/`bottom`); omit it to
render the whole page. Then open the PNG, read the table/equation, and rewrite
that block of the Markdown by hand (tables as clean pipe rows, math as `$…$` /
`$$…$$`), and re-run `verify_extraction.py` until it reports clean.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def render(pdf: str, page: int, bbox=None, out: str | None = None, dpi: int = 300):
    import fitz  # PyMuPDF

    doc = fitz.open(pdf)
    try:
        pg = doc[page - 1]
        zoom = dpi / 72.0
        clip = fitz.Rect(*bbox) if bbox else None
        pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
        out = out or f"{Path(pdf).with_suffix('')}.p{page}.png"
        pix.save(out)
        return out, pix.width, pix.height
    finally:
        doc.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Render a PDF page/region to PNG for read-and-rewrite repair.")
    ap.add_argument("pdf")
    ap.add_argument("--page", type=int, required=True, help="1-indexed page number")
    ap.add_argument("--bbox", default=None, help="x0,y0,x1,y1 in PDF points (top-left origin); omit for whole page")
    ap.add_argument("-o", "--out", default=None, help="output PNG path (default: <pdf>.p<N>.png)")
    ap.add_argument("--dpi", type=int, default=300, help="render resolution (default 300)")
    args = ap.parse_args()

    bbox = tuple(float(v) for v in args.bbox.split(",")) if args.bbox else None
    out, w, h = render(args.pdf, args.page, bbox, args.out, args.dpi)
    print(f"[render] {out} ({w}x{h}) — open it, read the region, rewrite that block, re-run verify_extraction.py")


if __name__ == "__main__":
    main()
