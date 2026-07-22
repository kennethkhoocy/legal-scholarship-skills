from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TESTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = TESTS_DIR.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
CONVERT_PY = SCRIPTS_DIR / "convert.py"
INDEX_PATH = TESTS_DIR / "index.json"


SUMMARY_PATTERNS: dict[str, re.Pattern[str]] = {
    "tables_detected": re.compile(r"^Tables detected:\s*(.+)$", re.MULTILINE),
    "figures_detected": re.compile(r"^Figures detected:\s*(.+)$", re.MULTILINE),
    "tables_inserted": re.compile(r"^Tables inserted:\s*(.+)$", re.MULTILINE),
    "figures_inserted": re.compile(r"^Figures inserted:\s*(.+)$", re.MULTILINE),
    "footnotes": re.compile(r"^Footnotes:\s*(.+)$", re.MULTILINE),
    "equations": re.compile(r"^OMML equations:\s*(.+)$", re.MULTILINE),
    "unresolved": re.compile(r"^Unresolved placeholders:\s*(.+)$", re.MULTILINE),
    "refs": re.compile(r"^Unresolved reference commands:\s*(.+)$", re.MULTILINE),
}


def run_command(
    args: list[str],
    cwd: Path,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def test_directories() -> list[Path]:
    return sorted(
        path for path in TESTS_DIR.iterdir()
        if path.is_dir() and path.name.startswith("t")
    )


def find_tex(test_dir: Path) -> Path:
    preferred = test_dir / f"{test_dir.name}.tex"
    if preferred.exists():
        return preferred
    tex_files = sorted(test_dir.glob("*.tex"))
    if not tex_files:
        raise FileNotFoundError(f"No .tex source found in {test_dir}")
    if len(tex_files) > 1:
        raise RuntimeError(f"Multiple .tex sources found in {test_dir}; expected one")
    return tex_files[0]


def latexmk_args(tex_path: Path) -> list[str]:
    source = tex_path.read_text(encoding="utf-8", errors="replace")
    args = ["latexmk", "-interaction=nonstopmode", "-halt-on-error"]
    if re.search(r"%\s*!TEX\s+program\s*=\s*xelatex", source, re.IGNORECASE) or r"\usepackage{fontspec}" in source:
        args.append("-xelatex")
    else:
        args.append("-pdf")
    args.append(tex_path.name)
    return args


def compile_tex(tex_path: Path, name: str) -> tuple[Path | None, subprocess.CompletedProcess[str]]:
    proc = run_command(latexmk_args(tex_path), tex_path.parent, timeout=300)
    source_pdf = tex_path.with_suffix(".pdf")
    compiled_pdf = tex_path.parent / f"{name}_compiled.pdf"
    if proc.returncode == 0 and source_pdf.exists():
        if compiled_pdf.exists():
            compiled_pdf.unlink()
        shutil.copy2(source_pdf, compiled_pdf)
        return compiled_pdf, proc
    return None, proc


def convert_tex(tex_path: Path, name: str) -> tuple[Path, Path, subprocess.CompletedProcess[str], dict[str, Any] | None]:
    docx_path = tex_path.parent / f"{name}.docx"
    workdir = tex_path.parent / f"_{name}_convert_work"
    if docx_path.exists():
        docx_path.unlink()
    args = [
        sys.executable,
        str(CONVERT_PY),
        str(tex_path),
        "--out",
        str(docx_path),
        "--workdir",
        str(workdir),
        "--no-render",
    ]
    proc = run_command(args, SCRIPTS_DIR, timeout=360)
    summary_json = workdir / "conversion_summary.json"
    summary_data: dict[str, Any] | None = None
    if summary_json.exists():
        try:
            summary_data = json.loads(summary_json.read_text(encoding="utf-8"))
        except Exception:
            summary_data = None
    return docx_path, workdir, proc, summary_data


def render_docx_with_word(docx_path: Path, pdf_path: Path) -> tuple[str, list[str]]:
    messages: list[str] = []
    word = None
    try:
        import win32com.client  # type: ignore

        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(docx_path.resolve()))
        doc.ExportAsFixedFormat(str(pdf_path.resolve()), 17)
        doc.Close(False)
        if pdf_path.exists():
            return "word-com", messages
        messages.append("Word COM finished without producing the expected PDF")
    except Exception as exc:
        messages.append(f"Word COM failed: {type(exc).__name__}: {exc}")
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
    return "", messages


def render_docx_with_soffice(docx_path: Path, pdf_path: Path, test_dir: Path) -> tuple[str, list[str]]:
    messages: list[str] = []
    soffice = shutil.which("soffice.com") or shutil.which("soffice.exe") or shutil.which("soffice")
    if not soffice:
        return "", ["LibreOffice soffice was not found on PATH"]
    render_dir = test_dir / "_render_work"
    render_dir.mkdir(exist_ok=True)
    profile = render_dir / ".lo_profile"
    profile.mkdir(exist_ok=True)
    proc = run_command(
        [
            soffice,
            f"-env:UserInstallation={profile.resolve().as_uri()}",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(render_dir),
            str(docx_path),
        ],
        test_dir,
        timeout=240,
    )
    if proc.returncode != 0:
        messages.append(f"LibreOffice failed ({proc.returncode}): {proc.stderr.strip()}")
        return "", messages
    produced = render_dir / f"{docx_path.stem}.pdf"
    if produced.exists() and produced != pdf_path:
        if pdf_path.exists():
            pdf_path.unlink()
        produced.replace(pdf_path)
    if pdf_path.exists():
        return "libreoffice", messages
    messages.append("LibreOffice finished without producing the expected PDF")
    return "", messages


def render_docx_to_pdf(docx_path: Path, name: str) -> tuple[Path | None, str, list[str]]:
    pdf_path = docx_path.parent / f"{name}_converted.pdf"
    if pdf_path.exists():
        pdf_path.unlink()
    method, messages = render_docx_with_word(docx_path, pdf_path)
    if method:
        return pdf_path, method, messages
    fallback_method, fallback_messages = render_docx_with_soffice(docx_path, pdf_path, docx_path.parent)
    messages.extend(fallback_messages)
    if fallback_method:
        return pdf_path, fallback_method, messages
    return None, "", messages


def rasterize_pdf(pdf_path: Path, prefix: str, test_dir: Path, dpi: int = 150) -> int:
    import fitz

    for old in test_dir.glob(f"{prefix}_p*.png"):
        old.unlink()
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    with fitz.open(str(pdf_path)) as pdf:
        page_count = pdf.page_count
        for page_index in range(page_count):
            pix = pdf.load_page(page_index).get_pixmap(matrix=matrix, alpha=False)
            out = test_dir / f"{prefix}_p{page_index + 1:02d}.png"
            pix.save(str(out))
        return page_count


def value_from_stdout(stdout: str, key: str) -> Any:
    match = SUMMARY_PATTERNS[key].search(stdout)
    if not match:
        return None
    value = match.group(1).strip()
    if value.isdigit():
        return int(value)
    return value


def compact_convert_summary(proc: subprocess.CompletedProcess[str], summary_data: dict[str, Any] | None) -> dict[str, Any]:
    parsed = {key: value_from_stdout(proc.stdout, key) for key in SUMMARY_PATTERNS}
    summary: dict[str, Any] = {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "tables": {
            "detected": parsed["tables_detected"],
            "inserted": parsed["tables_inserted"],
        },
        "figures": {
            "detected": parsed["figures_detected"],
            "inserted": parsed["figures_inserted"],
        },
        "footnotes": parsed["footnotes"],
        "equations": parsed["equations"],
        "unresolved": parsed["unresolved"],
        "refs": parsed["refs"],
        "errors": [],
    }
    if proc.returncode != 0:
        summary["errors"].append(f"convert.py exited with status {proc.returncode}")
    if summary_data:
        verify = summary_data.get("verify", {})
        transform = summary_data.get("transform", {})
        assembly = summary_data.get("assembly", {})
        summary["json"] = {
            "tables_detected": transform.get("table_floats"),
            "figures_detected": transform.get("figure_floats"),
            "tables_inserted": len(assembly.get("tables_inserted", [])),
            "figures_inserted": len(assembly.get("figures_inserted", [])),
            "footnotes": verify.get("footnotes"),
            "equations": verify.get("omml_equations"),
            "unresolved": verify.get("unresolved_placeholders"),
            "refs": verify.get("unresolved_reference_commands"),
            "missing": assembly.get("missing", []),
        }
    return summary


def write_index(results: list[dict[str, Any]]) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tests": results,
    }
    tmp = INDEX_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(INDEX_PATH)


def run_one(test_dir: Path) -> dict[str, Any]:
    name = test_dir.name
    result: dict[str, Any] = {
        "name": name,
        "compiled_pages": None,
        "converted_pages": None,
        "convert_summary": None,
        "exceptions": [],
    }
    try:
        tex_path = find_tex(test_dir)
        compiled_pdf, latex_proc = compile_tex(tex_path, name)
        result["latexmk"] = {
            "returncode": latex_proc.returncode,
            "stdout": latex_proc.stdout,
            "stderr": latex_proc.stderr,
        }
        if compiled_pdf is None:
            result["exceptions"].append("latexmk did not produce a compiled PDF")
            return result
        result["compiled_pdf"] = str(compiled_pdf)
        result["compiled_pages"] = rasterize_pdf(compiled_pdf, "compiled", test_dir)

        docx_path, workdir, convert_proc, summary_data = convert_tex(tex_path, name)
        result["docx"] = str(docx_path)
        result["convert_workdir"] = str(workdir)
        result["convert_summary"] = compact_convert_summary(convert_proc, summary_data)
        if convert_proc.returncode != 0 or not docx_path.exists():
            result["exceptions"].append("convert.py did not produce a usable DOCX")
            return result

        converted_pdf, render_method, render_messages = render_docx_to_pdf(docx_path, name)
        result["render"] = {
            "method": render_method,
            "messages": render_messages,
        }
        if converted_pdf is None:
            result["exceptions"].append("DOCX rendering did not produce a converted PDF")
            return result
        result["converted_pdf"] = str(converted_pdf)
        result["converted_pages"] = rasterize_pdf(converted_pdf, "converted", test_dir)
        return result
    except Exception as exc:
        result["exceptions"].append(f"{type(exc).__name__}: {exc}")
        result["traceback"] = traceback.format_exc()
        return result


def main() -> int:
    results: list[dict[str, Any]] = []
    for test_dir in test_directories():
        result = run_one(test_dir)
        results.append(result)
        write_index(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
