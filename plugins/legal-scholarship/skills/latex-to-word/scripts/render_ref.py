# -*- coding: utf-8 -*-
"""Render one PDF page or crop rectangle to a PNG for visual QA."""
from __future__ import annotations

import argparse
from pathlib import Path

import fitz


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a PDF page to PNG, optionally cropped.")
    parser.add_argument("pdf")
    parser.add_argument("out")
    parser.add_argument("--page", type=int, default=1, help="One-based page number")
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--crop", nargs=4, type=float, metavar=("X0", "Y0", "X1", "Y1"))
    ns = parser.parse_args()

    pdf_path = Path(ns.pdf)
    out_path = Path(ns.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(str(pdf_path)) as doc:
        page = doc.load_page(ns.page - 1)
        clip = fitz.Rect(ns.crop) if ns.crop else None
        pix = page.get_pixmap(matrix=fitz.Matrix(ns.dpi / 72, ns.dpi / 72), clip=clip, alpha=False)
        pix.save(str(out_path))
    print(f"saved {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
