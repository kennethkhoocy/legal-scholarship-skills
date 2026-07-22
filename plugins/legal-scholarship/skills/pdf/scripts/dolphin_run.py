"""Wrapper that dispatches to the user's Dolphin demo scripts.

Activates the Dolphin venv, cds to the Dolphin install dir, and runs the
appropriate demo script (demo_page.py / demo_element.py / demo_layout.py) based
on --mode. Performs VRAM pre-check and verifies VRAM release after the run.

Usage:
    python dolphin_run.py --mode page --input <file_or_dir> --save_dir <out>
    python dolphin_run.py --mode element --input <img> --save_dir <out> --element_type table
    python dolphin_run.py --mode layout --input <file_or_dir> --save_dir <out>
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# Dolphin install dir: override with the DOLPHIN_DIR env var; defaults to ~/Dolphin.
DEFAULT_DOLPHIN_DIR = os.environ.get("DOLPHIN_DIR") or os.path.expanduser("~/Dolphin")
DEFAULT_MIN_VRAM_FREE_MB = 8_000

MODE_TO_SCRIPT = {
    "page": "demo_page.py",
    "element": "demo_element.py",
    "layout": "demo_layout.py",
}


def build_command(
    mode: str,
    input_path: str,
    save_dir: str,
    max_batch_size: int,
    element_type: str | None,
    dolphin_dir: str = DEFAULT_DOLPHIN_DIR,
    print_results: bool = False,
) -> list[str]:
    """Build the argv list to invoke the right Dolphin demo script.

    Per-mode flag matrix (must match the demo scripts in the Dolphin install dir,
    $DOLPHIN_DIR or default ~/Dolphin):
        page    : --max_batch_size  (demo_page.py:338)
        element : --element_type, --print_results  (demo_element.py:178, 190)
        layout  : (no extras)

    Raises ValueError on invalid mode, missing element_type for element mode,
    or print_results requested outside element mode.
    """
    if mode not in MODE_TO_SCRIPT:
        raise ValueError(f"Invalid mode: {mode!r}. Must be one of {list(MODE_TO_SCRIPT)}")
    if mode == "element" and not element_type:
        raise ValueError("--element_type is required when mode='element'")
    if print_results and mode != "element":
        # demo_page.py and demo_layout.py do not define --print_results;
        # silently passing it would cause an argparse error in the child.
        raise ValueError("--print_results is only supported in mode='element'")

    script = MODE_TO_SCRIPT[mode]
    venv_python = str(Path(dolphin_dir) / "dolphin-env" / "Scripts" / "python.exe")
    if not Path(venv_python).exists():
        # Fall back to interpreter on PATH; the venv activate is handled by env vars
        venv_python = sys.executable

    cmd = [
        venv_python,
        str(Path(dolphin_dir) / script),
        "--model_path", "./hf_model",
        "--input_path", input_path,
        "--save_dir", save_dir,
    ]
    if mode == "page":
        cmd += ["--max_batch_size", str(max_batch_size)]
    if mode == "element":
        cmd += ["--element_type", element_type]
        if print_results:
            cmd += ["--print_results"]
    return cmd


def dolphin_is_installed(dolphin_dir: str, mode: str) -> bool:
    """True if the Dolphin demo script for this mode exists under dolphin_dir.

    Dolphin is an OPTIONAL OCR backend. When it isn't installed this returns
    False so main() can abort with an actionable message instead of letting the
    child process die with a cryptic "No such file or directory".
    """
    script = MODE_TO_SCRIPT.get(mode)
    if script is None:
        return False
    return (Path(dolphin_dir) / script).exists()


def check_vram_free_mb() -> int | None:
    """Run nvidia-smi and return free VRAM in MiB on the first GPU, or None on failure."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    # Output looks like:
    #   memory.free [MiB]
    #   12345
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    try:
        return int(lines[1])
    except ValueError:
        return None


def verify_vram_released(stdout_text: str) -> bool:
    """Return True if Dolphin's "VRAM released: X MB remaining" marker is present."""
    return bool(re.search(r"VRAM released:\s*\d+\s*MB remaining", stdout_text))


def main():
    ap = argparse.ArgumentParser(description="Run Dolphin v2 with proper env/VRAM management.")
    ap.add_argument("--mode", choices=list(MODE_TO_SCRIPT), required=True)
    ap.add_argument("--input", dest="input_path", required=True, help="Input file or directory")
    ap.add_argument("--save_dir", required=True)
    ap.add_argument("--max_batch_size", type=int, default=4)
    ap.add_argument("--element_type", default=None, choices=["table", "formula", "text", "code"])
    ap.add_argument("--dolphin_dir", default=DEFAULT_DOLPHIN_DIR)
    ap.add_argument(
        "--min_vram_free_mb",
        type=int,
        default=DEFAULT_MIN_VRAM_FREE_MB,
        help="Abort if less than this much VRAM is free (default: 8000).",
    )
    ap.add_argument(
        "--print_results",
        action="store_true",
        default=False,
        help="(element mode only) Pass through --print_results to demo_element.py so "
             "recognition results are echoed to stdout in addition to being saved.",
    )
    args = ap.parse_args()

    if not dolphin_is_installed(args.dolphin_dir, args.mode):
        print(
            f"[abort] Dolphin not found at {args.dolphin_dir!r} "
            f"(expected {MODE_TO_SCRIPT[args.mode]} there). Dolphin is an OPTIONAL "
            f"OCR backend for scanned/photographed PDFs. Either install it and point "
            f"DOLPHIN_DIR (or --dolphin_dir) at it, or use a CPU fallback: "
            f"opendataloader-pdf for born-digital docs, or pytesseract + pdf2image for scans.",
            file=sys.stderr,
        )
        sys.exit(3)

    free_mb = check_vram_free_mb()
    if free_mb is None:
        print("[warn] Could not query nvidia-smi; proceeding without VRAM check.")
    elif free_mb < args.min_vram_free_mb:
        print(
            f"[abort] Only {free_mb} MB VRAM free; need at least {args.min_vram_free_mb} MB. "
            f"Options: (a) wait for other GPU jobs to finish, (b) use opendataloader-pdf "
            f"instead, (c) reduce --max_batch_size."
        )
        sys.exit(2)
    else:
        print(f"[info] {free_mb} MB VRAM free, proceeding.")

    cmd = build_command(
        mode=args.mode,
        input_path=args.input_path,
        save_dir=args.save_dir,
        max_batch_size=args.max_batch_size,
        element_type=args.element_type,
        dolphin_dir=args.dolphin_dir,
        print_results=args.print_results,
    )

    print(f"[info] Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=args.dolphin_dir,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if not verify_vram_released(result.stdout + result.stderr):
        print(
            "[warn] No 'VRAM released' marker found in output. "
            "Consider manually checking nvidia-smi and killing stray Python processes."
        )

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
