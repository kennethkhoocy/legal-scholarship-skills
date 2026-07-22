"""Convert a .docx to one image per page via soffice.py PDF + pdftoppm."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from anthropic_bridge import AnthropicSkillNotInstalledError, run_anthropic


def run(input_path: Path, out_dir: Path, dpi: int = 150) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: convert to PDF using Anthropic's soffice wrapper
    try:
        r1 = run_anthropic(
            "office/soffice.py",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(input_path),
            check=False,
        )
    except AnthropicSkillNotInstalledError as e:
        print(str(e), file=sys.stderr)
        return 2
    if r1.returncode != 0:
        if r1.stderr:
            print(r1.stderr, file=sys.stderr)
        return r1.returncode

    pdf_path = out_dir / (input_path.stem + ".pdf")
    if not pdf_path.is_file():
        # soffice may have placed it under a different stem; pick the first .pdf
        pdfs = list(out_dir.glob("*.pdf"))
        if not pdfs:
            print(f"PDF conversion produced no output in {out_dir}", file=sys.stderr)
            return 3
        pdf_path = pdfs[0]

    # Step 2: pdftoppm to JPEG
    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm is None:
        print("pdftoppm not on PATH. Install Poppler utilities.", file=sys.stderr)
        return 4

    r2 = subprocess.run(
        [pdftoppm, "-jpeg", "-r", str(dpi), str(pdf_path), str(out_dir / "page")],
        capture_output=True,
        text=True,
    )
    if r2.returncode != 0:
        if r2.stderr:
            print(r2.stderr, file=sys.stderr)
    return r2.returncode
