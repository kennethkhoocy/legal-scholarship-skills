# -*- coding: utf-8 -*-
"""Emit the generalized converter's detected table manifest as JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from convert import build_config, build_pandoc_tex, parse_args


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect table floats without creating a final DOCX.")
    parser.add_argument("main_tex")
    parser.add_argument("--aux")
    parser.add_argument("--tables-dir")
    parser.add_argument("--figures-dir")
    parser.add_argument("--font", default="Linux Libertine G")
    parser.add_argument("--workdir")
    parser.add_argument("--out")
    ns = parser.parse_args()
    if not ns.out:
        ns.out = str(Path(ns.main_tex).with_suffix(".docx"))
    ns.no_render = True
    config = build_config(ns)
    config.workdir.mkdir(parents=True, exist_ok=True)
    transform = build_pandoc_tex(config)
    print(json.dumps(transform["tables"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
