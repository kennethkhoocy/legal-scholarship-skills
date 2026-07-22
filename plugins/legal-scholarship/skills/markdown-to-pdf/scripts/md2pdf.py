#!/usr/bin/env python3
"""
md2pdf.py -- Convert GitHub-flavored Markdown to PDF with images preserved.

Pipeline: pandoc (GFM -> standalone HTML, resources embedded) -> headless
Chrome/Edge print-to-pdf -> pypdf verification that every referenced image
made it into the PDF.

Usage:
  python md2pdf.py README.md
  python md2pdf.py notes.md -o out/notes.pdf --keep-html
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CSS = SKILL_DIR / "assets" / "print.css"

BROWSER_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def find_browser(explicit):
    if explicit:
        if Path(explicit).exists():
            return explicit
        sys.exit(f"ERROR: --browser path not found: {explicit}")
    for name in ("chrome", "google-chrome", "chromium", "msedge"):
        path = shutil.which(name)
        if path:
            return path
    for cand in BROWSER_CANDIDATES:
        if Path(cand).exists():
            return cand
    sys.exit("ERROR: no Chrome/Chromium/Edge binary found. Pass --browser <path>.")


def run(cmd, **kw):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    except subprocess.TimeoutExpired:
        sys.exit(f"ERROR: {Path(cmd[0]).name} timed out.")
    if proc.returncode != 0:
        sys.exit(
            f"ERROR: {Path(cmd[0]).name} failed (exit {proc.returncode}):\n"
            f"{proc.stderr.strip()}"
        )
    return proc


def count_referenced_images(md_text):
    # Fenced code blocks may contain literal ![...] examples; ignore them.
    prose = re.sub(r"```.*?```", "", md_text, flags=re.S)
    return len(re.findall(r"!\[", prose)) + len(re.findall(r"<img\b", prose, re.I))


def verify(pdf_path, n_referenced):
    try:
        from pypdf import PdfReader
    except ImportError:
        print("NOTE: pypdf not installed -- skipping image verification (pip install pypdf).")
        return 0
    reader = PdfReader(str(pdf_path))
    embedded = 0
    for i, page in enumerate(reader.pages, start=1):
        xobjects = page.get("/Resources", {}).get("/XObject", {})
        for key in xobjects:
            obj = xobjects[key].get_object()
            if obj.get("/Subtype") == "/Image":
                embedded += 1
                print(f"  page {i}: image {obj.get('/Width')}x{obj.get('/Height')}")
    print(
        f"PDF: {len(reader.pages)} pages, {embedded} embedded raster images "
        f"({n_referenced} image references in the Markdown)."
    )
    if embedded < n_referenced:
        print(
            "WARNING: fewer images embedded than referenced. Likely causes: an "
            "image fetch failed (check the URL/path), or an SVG rendered as "
            "vector art (no raster XObject) -- inspect the PDF visually."
        )
        return 2
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("input", help="Markdown file (GFM)")
    ap.add_argument("-o", "--output", help="output PDF path (default: alongside the input)")
    ap.add_argument("--css", default=str(DEFAULT_CSS), help="print stylesheet to apply")
    ap.add_argument("--browser", help="explicit Chrome/Chromium/Edge binary path")
    ap.add_argument(
        "--no-embed",
        action="store_true",
        help="skip pandoc --embed-resources; the browser fetches images at print time",
    )
    ap.add_argument("--keep-html", action="store_true", help="keep the intermediate HTML beside the PDF")
    ap.add_argument(
        "--budget",
        type=int,
        default=30000,
        help="Chrome --virtual-time-budget in ms; raise for many/slow remote images",
    )
    ap.add_argument("--no-verify", action="store_true", help="skip pypdf image verification")
    args = ap.parse_args()

    md = Path(args.input).resolve()
    if not md.is_file():
        sys.exit(f"ERROR: not a file: {md}")
    out = Path(args.output).resolve() if args.output else md.with_suffix(".pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    css = Path(args.css).resolve()
    if not css.is_file():
        sys.exit(f"ERROR: stylesheet not found: {css}")

    pandoc = shutil.which("pandoc")
    if not pandoc:
        sys.exit("ERROR: pandoc not on PATH (https://pandoc.org/installing.html).")
    browser = find_browser(args.browser)

    with tempfile.TemporaryDirectory(prefix="md2pdf_") as td:
        html = Path(td) / (md.stem + ".html")
        cmd = [
            pandoc, str(md), "-f", "gfm", "-t", "html5", "--standalone",
            "--metadata", f"pagetitle={md.stem}", "-o", str(html),
        ]
        if args.no_embed:
            shutil.copy(css, Path(td) / "print.css")
            cmd += ["-c", "print.css"]
        else:
            cmd += ["--embed-resources", "-c", str(css)]
        # cwd = the markdown's directory so relative local image paths resolve.
        print(f"[1/3] pandoc -> {html.name}")
        run(cmd, cwd=str(md.parent), timeout=300)

        # Print into the temp dir, then move: Chrome can fail to overwrite a
        # file in a cloud-synced directory (Dropbox/OneDrive lock) while still
        # exiting 0, which would silently leave a stale PDF at the target.
        tmp_pdf = Path(td) / (md.stem + ".pdf")
        print(f"[2/3] {Path(browser).name} print-to-pdf -> {out}")
        run(
            [
                browser, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                f"--virtual-time-budget={args.budget}",
                f"--print-to-pdf={tmp_pdf}", html.as_uri(),
            ],
            timeout=600,
        )
        if not tmp_pdf.is_file() or tmp_pdf.stat().st_size == 0:
            sys.exit("ERROR: the browser produced no output PDF.")
        for attempt in range(5):
            try:
                if out.exists():
                    out.unlink()
                shutil.move(str(tmp_pdf), str(out))
                break
            except PermissionError:
                if attempt == 4:
                    fallback = out.with_name(out.stem + ".new.pdf")
                    if fallback.exists():
                        fallback.unlink()
                    shutil.move(str(tmp_pdf), str(fallback))
                    sys.exit(
                        f"ERROR: {out} is locked by another process (open PDF "
                        f"viewer or cloud sync). Fresh PDF saved to {fallback}; "
                        f"close the viewer and rename it over the target."
                    )
                time.sleep(2)

        if args.keep_html:
            kept = out.with_suffix(".html")
            shutil.copy(html, kept)
            if args.no_embed:
                shutil.copy(css, kept.parent / "print.css")
            print(f"      kept intermediate HTML: {kept}")

    if not out.is_file() or out.stat().st_size == 0:
        sys.exit("ERROR: the browser produced no output PDF.")
    rc = 0
    if not args.no_verify:
        print("[3/3] verify")
        rc = verify(out, count_referenced_images(md.read_text(encoding="utf-8", errors="replace")))
    print(f"DONE: {out} ({out.stat().st_size:,} bytes)")
    sys.exit(rc)


if __name__ == "__main__":
    main()
