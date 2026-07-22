# -*- coding: utf-8 -*-
"""Render PDF page(s) to PNG. Usage: pdf_to_png.py <in.pdf> <out.png> [dpi] [page]"""
import sys, fitz
pdf, out = sys.argv[1], sys.argv[2]
dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 300
page = int(sys.argv[4]) if len(sys.argv) > 4 else 0
doc = fitz.open(pdf)
mat = fitz.Matrix(dpi / 72, dpi / 72)
p = doc[page]
p.get_pixmap(matrix=mat).save(out)
print(f"saved {out}  ({len(doc)} pages, page {page}, {p.rect})")
