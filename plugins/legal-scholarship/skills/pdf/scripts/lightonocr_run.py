"""LightOnOCR-2-1B runner: scanned PDF (or image) -> Markdown, on GPU.

Primary OCR backend for scanned/photographed PDFs (replaces Dolphin v2 as the
default; dolphin_run.py remains as fallback). 1B-param end-to-end VLM, ~3 GB
VRAM in bf16, LaTeX-aware. Model weights auto-download from Hugging Face on
first run (~2.5 GB, cached under ~/.cache/huggingface).

Lives outside the venv: when invoked with any Python it re-execs itself under
the LightOnOCR venv (LIGHTONOCR_DIR env var, default ~/LightOnOCR) where
torch cu130 + transformers v5 are installed.

Usage:
    python lightonocr_run.py <input.pdf|image> -o <output.md> [--pages 1-5]
"""

from __future__ import annotations

import argparse
import gc
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_DIR = os.environ.get("LIGHTONOCR_DIR") or os.path.expanduser("~/LightOnOCR")
MODEL_ID = "lightonai/LightOnOCR-2-1B"
DEFAULT_MIN_VRAM_FREE_MB = 4_000  # 1B model: ~3 GB in bf16
LONG_SIDE = 1540  # px; LightOnOCR's recommended render resolution


def parse_pages(spec: str | None, n_pages: int) -> list[int]:
    """'1-5' / '3' / '1,4,7' (1-based) -> 0-based page indices, clamped to doc.

    Clamps BEFORE expanding (so '1-999999999' never materializes a huge list)
    and de-duplicates while preserving order. A reversed range ('5-3') selects
    nothing; the caller fails on an empty overall selection.
    """
    if not spec:
        return list(range(n_pages))
    out: list[int] = []
    seen: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            candidates = range(max(int(a) - 1, 0), min(int(b), n_pages))
        else:
            candidates = [int(part) - 1]
        for p in candidates:
            if 0 <= p < n_pages and p not in seen:
                seen.add(p)
                out.append(p)
    return out


def check_vram_free_mb() -> int | None:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,nounits"],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    if r.returncode != 0 or len(lines) < 2:
        return None
    try:
        return int(lines[1])
    except ValueError:
        return None


def reexec_in_venv() -> None:
    """Re-launch this script under the LightOnOCR venv python (once)."""
    venv_dir = Path(DEFAULT_DIR) / "venv"
    win, posix = venv_dir / "Scripts" / "python.exe", venv_dir / "bin" / "python"
    venv_python = win if win.exists() or os.name == "nt" else posix
    if os.environ.get("_LIGHTONOCR_VENV") == "1":
        return  # already re-execed; run with whatever interpreter we have
    if Path(sys.executable).resolve() == venv_python.resolve():
        return
    if not venv_python.exists():
        print(
            f"[abort] LightOnOCR venv not found at {venv_python}. Create it with:\n"
            f"  python -m venv {DEFAULT_DIR}\\venv\n"
            f"  {DEFAULT_DIR}\\venv\\Scripts\\python -m pip install torch --index-url https://download.pytorch.org/whl/cu130\n"
            f"  {DEFAULT_DIR}\\venv\\Scripts\\python -m pip install transformers pillow pypdfium2 accelerate\n"
            f"Fallback OCR: dolphin_run.py, or pytesseract + pdf2image (CPU).",
            file=sys.stderr,
        )
        sys.exit(3)
    env = dict(os.environ, _LIGHTONOCR_VENV="1")
    raise SystemExit(subprocess.run([str(venv_python), *sys.argv], env=env).returncode)


def render_pages(input_path: Path, pages_spec: str | None):
    """Yield (1-based page number, PIL image) at LONG_SIDE resolution."""
    from PIL import Image

    if input_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        if pages_spec:
            print(f"[warn] --pages ignored for image input {input_path.name}")
        img = Image.open(input_path).convert("RGB")
        yield 1, img
        return

    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(input_path))
    try:
        indices = parse_pages(pages_spec, len(doc))
        for i in indices:
            page = doc[i]
            w, h = page.get_size()
            scale = LONG_SIDE / max(w, h)
            yield i + 1, page.render(scale=scale).to_pil().convert("RGB")
    finally:
        doc.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="LightOnOCR-2-1B: scanned PDF/image -> Markdown")
    ap.add_argument("input", help="PDF or image file")
    ap.add_argument("-o", "--output", required=True, help="Output .md path")
    ap.add_argument("--pages", default=None, help="1-based pages, e.g. '1-5' or '2,7'")
    ap.add_argument("--max-new-tokens", type=int, default=6144, help="Per-page generation cap")
    ap.add_argument("--model", default=MODEL_ID)
    ap.add_argument("--min-vram-free-mb", type=int, default=DEFAULT_MIN_VRAM_FREE_MB)
    args = ap.parse_args()

    input_path = Path(args.input)
    out_path = Path(args.output)
    if not input_path.is_file():
        print(f"[abort] Input not found: {input_path}", file=sys.stderr)
        sys.exit(2)
    if input_path.resolve() == out_path.resolve():
        print("[abort] Output path equals input path; refusing to overwrite the source file.", file=sys.stderr)
        sys.exit(2)

    reexec_in_venv()

    free_mb = check_vram_free_mb()
    if free_mb is None:
        print("[warn] Could not query nvidia-smi; proceeding without VRAM check.")
    elif free_mb < args.min_vram_free_mb:
        print(
            f"[abort] Only {free_mb} MB VRAM free; need {args.min_vram_free_mb} MB. "
            f"Wait for other GPU jobs or free VRAM first."
        )
        sys.exit(2)
    else:
        print(f"[info] {free_mb} MB VRAM free, proceeding.")

    import torch
    from transformers import LightOnOcrForConditionalGeneration, LightOnOcrProcessor

    # HARD REQUIREMENT: GPU only. Never fall back to CPU silently.
    if not torch.cuda.is_available():
        print(
            "[abort] CUDA is not available in the LightOnOCR venv — GPU is required. "
            "Refusing to run on CPU. Check the venv's torch install "
            "(pip install torch --index-url https://download.pytorch.org/whl/cu130).",
            file=sys.stderr,
        )
        sys.exit(2)
    device, dtype = "cuda", torch.bfloat16
    model = None
    try:
        print(f"[info] Loading {args.model} on {device} ({dtype}) ...")
        model = LightOnOcrForConditionalGeneration.from_pretrained(args.model, torch_dtype=dtype).to(device)
        processor = LightOnOcrProcessor.from_pretrained(args.model)
        param_device = next(model.parameters()).device
        if param_device.type != "cuda":
            print(f"[abort] Model landed on {param_device}, not the GPU.", file=sys.stderr)
            sys.exit(2)
        print(f"[info] model device: {param_device}, "
              f"VRAM allocated by torch: {torch.cuda.memory_allocated() // 2**20} MB")

        parts: list[str] = []
        for page_no, img in render_pages(input_path, args.pages):
            conversation = [{"role": "user", "content": [{"type": "image", "image": img}]}]
            inputs = processor.apply_chat_template(
                conversation, add_generation_prompt=True, tokenize=True,
                return_dict=True, return_tensors="pt",
            ).to(device)
            with torch.inference_mode():
                out = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
            n_prompt = inputs["input_ids"].shape[1]
            text = processor.decode(out[0][n_prompt:], skip_special_tokens=True).strip()
            del inputs, out
            parts.append(text)
            print(f"[info] page {page_no}: {len(text)} chars")

        if not any(p.strip() for p in parts):
            print(
                "[error] OCR produced no text (empty page selection or blank output) — "
                "not writing an empty file. Check --pages against the document; if the "
                "input is sound, fall back to dolphin_run.py.",
                file=sys.stderr,
            )
            sys.exit(1)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
        print(f"[info] Wrote {out_path} ({len(parts)} pages)")
    finally:
        # Release GPU on every exit path and print the marker the pdf skill's
        # verification step greps for.
        if model is not None:
            del model
        gc.collect()
        if device == "cuda":
            torch.cuda.empty_cache()
        remaining = check_vram_free_mb()
        if remaining is not None:
            print(f"VRAM released: {remaining} MB remaining")
        else:
            print("VRAM released: unknown MB remaining")


if __name__ == "__main__":
    main()
