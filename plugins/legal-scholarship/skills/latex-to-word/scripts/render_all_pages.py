# -*- coding: utf-8 -*-
"""Rasterise every page of a PDF. Usage: render_all_pages.py <pdf> <outdir> [dpi]"""
import sys, os, fitz
pdf, outdir = sys.argv[1], sys.argv[2]
dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 200
os.makedirs(outdir, exist_ok=True)
doc = fitz.open(pdf)
mat = fitz.Matrix(dpi / 72, dpi / 72)
for i in range(len(doc)):
    doc[i].get_pixmap(matrix=mat).save(os.path.join(outdir, f"p{i+1:02d}.png"))
print(f"{len(doc)} pages -> {outdir}")
