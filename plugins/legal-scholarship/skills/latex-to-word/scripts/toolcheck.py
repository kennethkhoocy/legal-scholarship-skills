# -*- coding: utf-8 -*-
"""Shared external-tool detection.

Resolves external executables (pandoc, latexmk, xelatex) by consulting PATH
first and then a small set of generic Windows install locations built from
environment variables only (no hard-coded usernames).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


class ToolNotFoundError(RuntimeError):
    """Raised when a required external tool cannot be resolved."""


_INSTALL_HINTS = {
    "pandoc": "pandoc not found on PATH — install from pandoc.org",
    "latexmk": "latexmk not found on PATH — install a TeX distribution (MiKTeX or TeX Live)",
    "xelatex": "xelatex not found on PATH — install a TeX distribution (MiKTeX or TeX Live)",
}


def _windows_candidates(name: str) -> list[str]:
    """Per-tool Windows install locations, built from environment variables.

    Pandoc and the TeX tools live in different places, so branch on the tool
    rather than offering Pandoc-flavored paths to ``latexmk``/``xelatex``.
    """
    exe = name if name.lower().endswith(".exe") else f"{name}.exe"
    stem = Path(exe).stem.lower()
    program_files = os.environ.get("ProgramFiles")
    localappdata = os.environ.get("LOCALAPPDATA")
    candidates: list[str] = []
    if stem == "pandoc":
        if localappdata:
            candidates.append(str(Path(localappdata) / "Pandoc" / exe))
        if program_files:
            candidates.append(str(Path(program_files) / "Pandoc" / exe))
        program_data = os.environ.get("ProgramData")
        if program_data:
            candidates.append(str(Path(program_data) / "chocolatey" / "bin" / exe))
    else:
        # TeX tools (latexmk, xelatex, ...): MiKTeX then TeX Live.
        if program_files:
            candidates.append(str(Path(program_files) / "MiKTeX" / "miktex" / "bin" / "x64" / exe))
        if localappdata:
            candidates.append(str(Path(localappdata) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64" / exe))
        texlive_root = Path(r"C:\texlive")
        if texlive_root.is_dir():
            for arch in ("windows", "win32"):
                candidates.extend(
                    str(match) for match in sorted(texlive_root.glob(f"*/bin/{arch}/{exe}"))
                )
    return candidates


def find_tool(name: str, extra_candidates: tuple[str, ...] = ()) -> str:
    """Resolve *name* to an executable path, or return "" when unresolved.

    Tries ``shutil.which`` first, then generic Windows install locations built
    from environment variables, then any caller-supplied extra candidates.
    A candidate resolves when the file exists.
    """
    on_path = shutil.which(name)
    if on_path:
        return on_path
    for candidate in list(_windows_candidates(name)) + list(extra_candidates):
        if candidate and Path(candidate).is_file():
            return candidate
    return ""


def _require(name: str) -> str:
    tool = find_tool(name)
    if not tool:
        raise ToolNotFoundError(_INSTALL_HINTS.get(name, f"{name} not found on PATH"))
    return tool


def find_pandoc() -> str:
    return _require("pandoc")


def find_latexmk() -> str:
    return _require("latexmk")


def find_xelatex() -> str:
    return _require("xelatex")


if __name__ == "__main__":
    for _name in ("pandoc", "latexmk", "xelatex"):
        _resolved = find_tool(_name)
        print(f"{_name}: {_resolved if _resolved else 'NOT FOUND'}")
