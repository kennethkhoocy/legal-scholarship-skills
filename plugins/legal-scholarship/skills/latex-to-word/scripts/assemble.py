# -*- coding: utf-8 -*-
"""Compatibility entry point for the generalized converter.

Assembly is now part of convert.py so table routing can use the same float
records that were created during body preparation.
"""
from __future__ import annotations

from convert import main


if __name__ == "__main__":
    raise SystemExit(main())
