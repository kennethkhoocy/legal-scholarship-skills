# -*- coding: utf-8 -*-
"""Print the text in the last row of each table in a DOCX."""
from __future__ import annotations

import argparse
from pathlib import Path

from docx import Document


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the last row of every DOCX table.")
    parser.add_argument("docx")
    ns = parser.parse_args()
    docx_path = Path(ns.docx)
    doc = Document(docx_path)
    for idx, table in enumerate(doc.tables, start=1):
        if not table.rows:
            print(f"table {idx}: <empty>")
            continue
        cells = [cell.text for cell in table.rows[-1].cells]
        print(f"table {idx}: {cells}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
