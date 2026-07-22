# -*- coding: utf-8 -*-
"""Compatibility entry point for documents whose tables include estout fragments.

The generalized converter detects estout fragments per float and builds them
with tex_table_to_docx.add_estout_table during assembly.
"""
from __future__ import annotations

from convert import main


if __name__ == "__main__":
    raise SystemExit(main())
