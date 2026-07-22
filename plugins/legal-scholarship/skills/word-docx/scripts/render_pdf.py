"""Render a .docx file to PDF using LibreOffice in headless mode.

Searches for ``soffice`` on the system PATH and in common Windows install
locations.  If LibreOffice is available, the document is converted via::

    soffice --headless --convert-to pdf --outdir <dir> <input>

If LibreOffice cannot be found, a diagnostic error is returned with
installation guidance.  No Windows COM automation is attempted.

Typical usage::

    from pathlib import Path
    from render_pdf import render_pdf

    diagnostics = render_pdf(Path("output.docx"), Path("output.pdf"))
    for d in diagnostics:
        print(f"[{d.level}] {d.message}")
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from models import DiagnosticEntry

logger = logging.getLogger(__name__)

# Common LibreOffice install paths on Windows, checked when shutil.which
# does not find soffice on PATH.
_WINDOWS_SOFFICE_PATHS: list[Path] = [
    Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
    Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
]


def _find_soffice() -> Path | None:
    """Locate the ``soffice`` executable.

    Checks the system PATH first (via ``shutil.which``), then falls back to
    well-known Windows installation directories.
    """
    for name in ("soffice", "soffice.exe"):
        found = shutil.which(name)
        if found:
            return Path(found)

    for candidate in _WINDOWS_SOFFICE_PATHS:
        if candidate.exists():
            return candidate

    return None


def render_pdf(
    input_path: Path,
    output_path: Path,
    verbose: bool = False,
) -> list[DiagnosticEntry]:
    """Convert a ``.docx`` to PDF via LibreOffice headless.

    Parameters
    ----------
    input_path:
        Path to the source ``.docx`` file.
    output_path:
        Desired path for the resulting PDF.
    verbose:
        When ``True``, log the LibreOffice command and its stdout/stderr.

    Returns
    -------
    list[DiagnosticEntry]
        Diagnostics covering success, failure, or LibreOffice availability.
    """
    diagnostics: list[DiagnosticEntry] = []
    input_path = Path(input_path).resolve()
    output_path = Path(output_path).resolve()

    # ── Validate input ────────────────────────────────────────────────
    if not input_path.exists():
        diagnostics.append(DiagnosticEntry(
            level="error", source="render_pdf",
            message=f"Input file not found: {input_path}",
        ))
        return diagnostics

    # ── Locate soffice ────────────────────────────────────────────────
    soffice = _find_soffice()
    if soffice is None:
        diagnostics.append(DiagnosticEntry(
            level="error", source="render_pdf",
            message=(
                "LibreOffice not found. Install LibreOffice for PDF "
                "rendering, or use Microsoft Word manually."
            ),
        ))
        return diagnostics

    diagnostics.append(DiagnosticEntry(
        level="info", source="render_pdf",
        message=f"Using LibreOffice at {soffice}",
    ))

    # ── Run conversion ────────────────────────────────────────────────
    # LibreOffice writes the PDF into --outdir with the same stem as the
    # input file.  We convert into the desired output directory and rename
    # afterward if the stem or directory differs.
    outdir = output_path.parent
    outdir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(soffice),
        "--headless",
        "--convert-to", "pdf",
        "--outdir", str(outdir),
        str(input_path),
    ]

    if verbose:
        logger.info("Running: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        diagnostics.append(DiagnosticEntry(
            level="error", source="render_pdf",
            message="LibreOffice conversion timed out after 120 seconds",
        ))
        return diagnostics
    except Exception as exc:
        diagnostics.append(DiagnosticEntry(
            level="error", source="render_pdf",
            message=f"Failed to run LibreOffice: {exc}",
        ))
        return diagnostics

    if verbose:
        if result.stdout.strip():
            logger.info("soffice stdout: %s", result.stdout.strip())
        if result.stderr.strip():
            logger.warning("soffice stderr: %s", result.stderr.strip())

    if result.returncode != 0:
        diagnostics.append(DiagnosticEntry(
            level="error", source="render_pdf",
            message=(
                f"LibreOffice exited with code {result.returncode}. "
                f"stderr: {result.stderr.strip()}"
            ),
        ))
        return diagnostics

    # ── Rename output if necessary ────────────────────────────────────
    # LibreOffice produces <input_stem>.pdf in outdir.
    lo_output = outdir / f"{input_path.stem}.pdf"

    if not lo_output.exists():
        diagnostics.append(DiagnosticEntry(
            level="error", source="render_pdf",
            message=(
                f"LibreOffice reported success but expected output "
                f"{lo_output.name} was not found in {outdir}"
            ),
        ))
        return diagnostics

    if lo_output != output_path:
        try:
            lo_output.rename(output_path)
        except Exception as exc:
            diagnostics.append(DiagnosticEntry(
                level="warning", source="render_pdf",
                message=(
                    f"Could not rename {lo_output.name} to "
                    f"{output_path.name}: {exc}. PDF is at {lo_output}"
                ),
            ))
            return diagnostics

    diagnostics.append(DiagnosticEntry(
        level="info", source="render_pdf",
        message=f"Rendered PDF to {output_path}",
    ))
    return diagnostics


# ── CLI entry point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Render a .docx to PDF via LibreOffice",
    )
    parser.add_argument("input", type=Path, help="Path to the .docx file")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output PDF path (defaults to <input_stem>.pdf in same directory)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Print LibreOffice command output",
    )
    args = parser.parse_args()

    input_path = args.input.resolve()
    out = args.output or input_path.with_suffix(".pdf")

    diags = render_pdf(input_path, out.resolve(), verbose=args.verbose)
    has_errors = False
    for d in diags:
        print(f"[{d.level.upper()}] {d.source}: {d.message}")
        if d.level == "error":
            has_errors = True
    if has_errors:
        sys.exit(1)
