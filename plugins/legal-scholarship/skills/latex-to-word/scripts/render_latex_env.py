# -*- coding: utf-8 -*-
"""Render standalone LaTeX environments to cached PNG images."""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

import toolcheck


Runner = Callable[[list[str], Path, int | None], subprocess.CompletedProcess[str]]


_FILECONTENTS_RE = re.compile(
    r"\\begin\{filecontents\*?\}(?:\[[^\]]*\])?\{[^{}]*\}.*?\\end\{filecontents\*?\}",
    re.DOTALL,
)


def _default_runner(command: list[str], cwd: Path, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def _strip_documentclass(text: str) -> str:
    return re.sub(r"\\documentclass(?:\[[^\]]*\])?\{[^{}]+\}", "", text)


def _remove_group_command(text: str, command: str) -> str:
    return re.sub(rf"\\{re.escape(command)}(?:\[[^\]]*\])?\{{[^{{}}]*\}}", "", text)


def _remove_layout_packages(text: str) -> str:
    layout_packages = {"geometry", "fullpage", "typearea"}

    def repl(match: re.Match[str]) -> str:
        packages = [part.strip() for part in match.group(1).split(",")]
        if any(package in layout_packages for package in packages):
            return ""
        return match.group(0)

    text = re.sub(r"\\usepackage(?:\[[^\]]*\])?\{([^{}]+)\}", repl, text)
    text = re.sub(r"\\geometry\{[^{}]*\}", "", text)
    text = re.sub(r"\\(?:pagestyle|thispagestyle)\{[^{}]*\}", "", text)
    text = re.sub(r"\\setlength\{\\(?:textwidth|textheight|oddsidemargin|evensidemargin|topmargin)\}\{[^{}]*\}", "", text)
    return text


def _has_package(preamble: str, package: str) -> bool:
    pkg_re = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{([^{}]+)\}")
    for match in pkg_re.finditer(preamble):
        packages = [part.strip() for part in match.group(1).split(",")]
        if package in packages:
            return True
    return False


def curated_preamble(raw_preamble: str, env_source: str = "") -> str:
    """Keep author macros and graphics packages while removing document-level setup."""
    preamble = _FILECONTENTS_RE.sub("", raw_preamble)
    begin_doc = re.search(r"\\begin\{document\}", preamble)
    if begin_doc:
        preamble = preamble[: begin_doc.start()]
    preamble = _strip_documentclass(preamble)
    for command in ("title", "author", "date", "bibliographystyle", "bibliography", "addbibresource"):
        preamble = _remove_group_command(preamble, command)
    preamble = re.sub(r"\\maketitle\b", "", preamble)
    preamble = _remove_layout_packages(preamble)

    additions: list[str] = []
    if not _has_package(preamble, "graphicx"):
        additions.append(r"\usepackage{graphicx}")
    if not _has_package(preamble, "float"):
        additions.append(r"\usepackage{float}")
    if re.search(r"\\begin\{(?:tikzpicture|pgfpicture)\}", env_source) and not _has_package(preamble, "tikz"):
        additions.append(r"\usepackage{tikz}")
    if r"\begin{axis}" in env_source and not _has_package(preamble, "pgfplots"):
        additions.append(r"\usepackage{pgfplots}")
        additions.append(r"\pgfplotsset{compat=1.18}")
    if r"\begin{algorithm" in env_source and not _has_package(preamble, "algorithm2e"):
        additions.append(r"\usepackage[ruled,vlined,linesnumbered]{algorithm2e}")

    lines = [line.rstrip() for line in preamble.splitlines() if line.strip()]
    lines.extend(additions)
    return "\n".join(lines).strip()


def _needs_xelatex(text: str) -> bool:
    return bool(
        re.search(r"%\s*!TEX\s+program\s*=\s*xelatex", text, re.IGNORECASE)
        or r"\usepackage{fontspec}" in text
        or r"\usepackage[no-math]{fontspec}" in text
    )


def _standalone_document(env_source: str, preamble: str, extra_setup: str) -> str:
    parts = [
        r"\documentclass[border=4pt]{standalone}",
        preamble,
        extra_setup,
        r"\begin{document}",
        env_source,
        r"\end{document}",
        "",
    ]
    return "\n".join(part for part in parts if part.strip())


def _preview_document(env_source: str, preamble: str, extra_setup: str) -> str:
    parts = [
        r"\documentclass{article}",
        preamble,
        r"\usepackage[active,tightpage]{preview}",
        r"\PreviewEnvironment{tikzpicture}",
        r"\PreviewEnvironment{pgfpicture}",
        r"\PreviewEnvironment{axis}",
        r"\PreviewEnvironment{algorithm}",
        extra_setup,
        r"\begin{document}",
        r"\begin{preview}",
        env_source,
        r"\end{preview}",
        r"\end{document}",
        "",
    ]
    return "\n".join(part for part in parts if part.strip())


def _compile_pdf(
    tex_path: Path,
    document: str,
    build_dir: Path,
    use_xelatex: bool,
    runner: Runner,
) -> Path | None:
    tex_path.write_text(document, encoding="utf-8", newline="\n")
    pdf_path = tex_path.with_suffix(".pdf")
    if pdf_path.exists():
        pdf_path.unlink()
    try:
        latexmk = toolcheck.find_latexmk()
    except toolcheck.ToolNotFoundError as exc:
        (build_dir / f"{tex_path.stem}_failure.txt").write_text(str(exc), encoding="utf-8")
        print(f"[render_latex_env] {exc}; skipping environment render", file=sys.stderr)
        return None
    command = [latexmk, "-interaction=nonstopmode", "-halt-on-error", "-xelatex" if use_xelatex else "-pdf", tex_path.name]
    try:
        proc = runner(command, build_dir, 180)
    except Exception as exc:  # noqa: BLE001 - render failure must be non-fatal.
        (build_dir / f"{tex_path.stem}_failure.txt").write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
        return None
    (build_dir / f"{tex_path.stem}_stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
    (build_dir / f"{tex_path.stem}_stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
    if proc.returncode != 0 or not pdf_path.exists():
        return None
    return pdf_path


def _rasterize_first_page(pdf_path: Path, out_path: Path) -> Path | None:
    try:
        import fitz

        with fitz.open(str(pdf_path)) as pdf:
            if pdf.page_count < 1:
                return None
            pix = pdf.load_page(0).get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), alpha=False)
            pix.save(str(out_path))
    except Exception:  # noqa: BLE001 - caller treats this as an omitted image.
        return None
    return out_path if out_path.exists() and out_path.stat().st_size > 0 else None


def render_env_to_png(
    env_source: str,
    preamble: str,
    config,
    *,
    extra_setup: str = "",
    run_command: Runner | None = None,
) -> Path | None:
    """Compile a LaTeX environment and rasterize its first PDF page to a cached PNG."""
    try:
        cleaned_preamble = curated_preamble(preamble, env_source)
        key_material = "\n".join([env_source, cleaned_preamble, extra_setup])
        key = hashlib.sha1(key_material.encode("utf-8")).hexdigest()
        cache_root = Path(config.workdir) / "_env_images"
        build_dir = cache_root / key[:12]
        build_dir.mkdir(parents=True, exist_ok=True)
        out_path = build_dir / f"{key[:12]}.png"
        if out_path.exists() and out_path.stat().st_size > 0:
            return out_path

        runner = run_command or _default_runner
        use_xelatex = _needs_xelatex("\n".join([preamble, env_source]))
        variants = [
            ("env_standalone.tex", _standalone_document(env_source, cleaned_preamble, extra_setup)),
            ("env_preview.tex", _preview_document(env_source, cleaned_preamble, extra_setup)),
        ]
        for filename, document in variants:
            pdf_path = _compile_pdf(build_dir / filename, document, build_dir, use_xelatex, runner)
            if pdf_path is None:
                continue
            rendered = _rasterize_first_page(pdf_path, out_path)
            if rendered is not None:
                return rendered
    except Exception:  # noqa: BLE001 - environment rendering must never abort conversion.
        return None
    return None
