"""
opendataloader-pdf wrapper with tqdm progress bar and probe integration.

Defaults to hybrid mode with the CLI's built-in triage (--hybrid-mode auto): the
local Java parser handles every page, and only pages flagged as complex are routed
to the Docling backend. Pass --no-hybrid to skip the backend entirely and run
local-only.

When --probe-output points to a JSON file produced by scripts/probe_pdf.py, this
wrapper auto-derives enrichment flags from the classification:
  - scanned                → --force-ocr
  - formula_density > 0.1  → --enrich-formula

Usage:
    python opendataloader_convert.py <input.pdf> [--output-dir DIR] [--format FMT] \\
        [--no-hybrid] [--probe-output PROBE.JSON]
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm", "-q"])
    from tqdm import tqdm

try:
    from pypdf import PdfReader
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pypdf", "-q"])
    from pypdf import PdfReader


def count_pages(pdf_path: str) -> int:
    return len(PdfReader(pdf_path).pages)


_SIMPLE_RANGE_RE = re.compile(r"^\d+-\d+$")


def _progress_total_for_pages(pages_arg: str | None, total: int) -> int:
    """Compute the progress-bar total when --pages may select a subset.

    --pages None → use the whole-document page count.
    --pages "<start>-<end>" → end - start + 1 (clamped to >= 1).
    --pages anything else (e.g. "3,5,7-9") → fall back to the whole-document
    count; the caller will surface a [info] note so the bar isn't silently
    misleading.
    """
    if not pages_arg:
        return total
    m = _SIMPLE_RANGE_RE.match(pages_arg.strip())
    if not m:
        return total
    start_str, end_str = pages_arg.strip().split("-", 1)
    start, end = int(start_str), int(end_str)
    return max(1, end - start + 1)


def derive_backend_flags(probe_output_path: str) -> list[str]:
    """Read a probe JSON file and derive opendataloader-pdf-hybrid backend flags.

    Returns a list of flag tokens (possibly empty). Returns an empty list if the
    probe file is missing, unreadable, or doesn't contain the expected keys —
    never raises.

    These flags belong to the hybrid backend (opendataloader-pdf-hybrid), not
    to the converter (opendataloader-pdf). They must be passed to the backend
    Popen call, not to the converter command.
    """
    import json
    import os

    if not probe_output_path or not os.path.exists(probe_output_path):
        return []
    try:
        with open(probe_output_path, "r", encoding="utf-8") as f:
            probe = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    flags: list[str] = []
    if probe.get("classification") == "scanned":
        flags.append("--force-ocr")
    if probe.get("formula_density", 0.0) > 0.1:
        flags.append("--enrich-formula")
    return flags


# Backward-compat alias (will be removed in future cleanup)
derive_enrichment_flags = derive_backend_flags


def ensure_runner_safe_decode() -> None:
    """Make opendataloader_pdf's JAR runner tolerant of non-UTF-8 log bytes.

    The bundled Java JAR prints progress to stdout in the OS locale charset
    (cp1252 on Windows). opendataloader_pdf/runner.py decodes that stream with
    NO error handler, so a single accented byte (e.g. 0xf3 = 'o-acute' from
    author names like "Anton"/"Lopez") raises UnicodeDecodeError and aborts the
    whole conversion -- even though the JAR has already written the correct,
    UTF-8 .md. We idempotently inject errors="replace" into runner.py's
    subprocess calls so a stray log byte can never crash the run. The .md
    content is written by the JAR and is unaffected.

    Best-effort and self-healing: any failure (read-only site-packages, upstream
    refactor) is swallowed, and it re-applies itself after a pip upgrade wipes
    the patch.
    ponytail: string-replace patch on the known buggy line; if upstream refactors
    runner.py, the needle-not-found branch warns instead of silently failing.
    """
    try:
        import importlib.util

        spec = importlib.util.find_spec("opendataloader_pdf")
        if not spec or not spec.submodule_search_locations:
            return
        runner = Path(list(spec.submodule_search_locations)[0]) / "runner.py"
        if not runner.exists():
            return
        text = runner.read_text(encoding="utf-8")
        if 'errors="replace"' in text:
            return  # already hardened
        needle = "encoding=locale.getpreferredencoding(False),"
        if needle not in text:
            print(
                "[warn] could not harden opendataloader_pdf/runner.py (encoding line "
                "not found); a non-UTF-8 JAR log byte may still abort the run."
            )
            return
        runner.write_text(text.replace(needle, needle + ' errors="replace",'), encoding="utf-8")
        print(
            "[patch] hardened opendataloader_pdf/runner.py: added errors='replace' so "
            "non-UTF-8 JAR log bytes (accented author names) can't abort conversion."
        )
    except Exception as e:
        print(f"[warn] runner.py hardening skipped: {type(e).__name__}: {e}")


def _selfcheck() -> None:
    """Assert the hardening transform injects the guard and is idempotent."""
    needle = "encoding=locale.getpreferredencoding(False),"
    sample = f"                {needle}\n"
    once = sample.replace(needle, needle + ' errors="replace",')
    assert 'errors="replace"' in once, "guard not injected"
    twice = once if 'errors="replace"' in once else once.replace(needle, needle + ' errors="replace",')
    assert twice == once, "second application must be a no-op (idempotent)"
    print("ok: runner hardening transform injects guard and is idempotent")


def clean_fragments_in_place(md_path: Path) -> None:
    """Strip garbled vector-figure text fragments from a converted Markdown file.

    Best-effort and self-contained: imports the sibling cleaner module, rewrites
    the file in place when anything is removed, and prints a short report. Any
    failure is reported and swallowed so it never breaks a successful conversion.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import clean_garbled_fragments as cgf

        text = md_path.read_text(encoding="utf-8")
        cleaned, reports = cgf.clean(text)
        if reports:
            removed = sum(r["num_fragments"] for r in reports)
            md_path.write_text(cleaned, encoding="utf-8")
            print(f"[clean] Removed {len(reports)} garbled figure-text run(s), {removed} fragment line(s).")
        else:
            print("[clean] No garbled fragments detected.")
    except Exception as e:
        print(f"[warn] fragment cleanup skipped: {type(e).__name__}: {e}")


def sanitize_math_in_place(md_path: Path) -> None:
    """Make the converted Markdown's math KaTeX-safe.

    Wraps leaked alignment (`&` / `\\`) in `\\begin{aligned}` and suppresses
    equation blocks the KaTeX engine cannot render, so a downstream renderer
    never shows a parse-error string. Best-effort: any failure is reported and
    swallowed.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import sanitize_math as sm

        text = md_path.read_text(encoding="utf-8")
        validator = sm.KaTeXValidator(auto_install=True)
        out, report = sm.sanitize(text, validator)
        if report["wrapped"] or report["suppressed"]:
            md_path.write_text(out, encoding="utf-8")
            print(
                f"[math] mode={report['mode']}: wrapped {report['wrapped']} alignment block(s), "
                f"suppressed {report['suppressed']} unparseable block(s)."
            )
            if report["mode"] != "katex":
                print("[math] (KaTeX engine unavailable — ran heuristic fallback; "
                      "set PDF_SKILL_KATEX or install Node+katex for full validation.)")
        else:
            print("[math] No KaTeX-unsafe equations detected.")
    except Exception as e:
        print(f"[warn] math sanitize skipped: {type(e).__name__}: {e}")


def run_quality_gate(md_path: Path, probe_output: str | None = None) -> None:
    """Run verify_extraction.py as a non-fatal gate after conversion.

    Detection must happen on EVERY conversion, not when the operator remembers to
    look — Docling's table/formula failures are silent and look plausible. This
    prints line-numbered flags and the exact follow-up (positional re-extract for
    merged tables, hand-rebuild/lightonocr for broken equations). Best-effort: any
    failure is reported and swallowed so it never breaks a successful conversion.
    """
    try:
        import json as _json
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import verify_extraction as ve

        fd = None
        if probe_output and Path(probe_output).exists():
            try:
                fd = _json.loads(Path(probe_output).read_text(encoding="utf-8")).get("formula_density")
            except Exception:
                fd = None
        issues = ve.verify(md_path.read_text(encoding="utf-8"), fd)
        if not issues:
            print("[verify] clean — no merged tables, broken equations, or stray glyphs detected.")
            return
        kinds: dict[str, int] = {}
        for it in issues:
            kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
        summary = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
        print(f"[verify] {len(issues)} issue(s) to FIX BEFORE SHIPPING: {summary}")
        for it in sorted(issues, key=lambda x: x["line"])[:20]:
            print(f"  L{it['line']}: [{it['kind']}] {str(it['detail'])[:100]}")
            print(f"      -> {it['fix']}")
        print("[verify] merged table OR broken/flattened equation → render the page region with "
              "scripts/render_region.py --page N [--bbox x0,y0,x1,y1], read it, and rewrite that block "
              "from the image (extraction.md §4C); for an all-image math/scan paper, escalate to lightonocr.")
    except Exception as e:
        print(f"[warn] quality gate skipped: {type(e).__name__}: {e}")


def wait_for_health(url: str, timeout: int = 90, interval: int = 3) -> bool:
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=5)
            return True
        except Exception:
            time.sleep(interval)
    return False


def _terminate_proc_tree(proc: subprocess.Popen) -> None:
    """Terminate a backend process AND its children.

    The hybrid backend spawns Docling workers via multiprocessing.spawn. On
    Windows, terminating only the parent PID orphans those workers — they linger
    and soak CPU/RAM indefinitely. taskkill /T kills the whole tree. On POSIX,
    fall back to terminate()/kill() on the parent.
    """
    import platform

    if proc is None or proc.poll() is not None:
        return
    if platform.system() == "Windows":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, text=True, timeout=15,
            )
            return
        except Exception:
            pass  # fall through to the generic path
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _terminate_backend_on_port(port: int = 5002) -> None:
    """Best-effort: kill whatever process is listening on `port`.

    Cross-platform and defensive — every failure is swallowed and logged, never
    raised, because this is a convenience path for --restart-backend, not a
    correctness-critical operation.
    """
    import platform

    try:
        if platform.system() == "Windows":
            # netstat → PIDs on the port → taskkill each.
            out = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True, text=True, timeout=10,
            ).stdout
            pids = set()
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and (f":{port}" in parts[1]) and parts[3].upper() == "LISTENING":
                    pids.add(parts[4])
            for pid in pids:
                # /T kills the process tree so Docling's multiprocessing.spawn
                # workers are reaped along with the backend parent.
                subprocess.run(["taskkill", "/F", "/T", "/PID", pid],
                               capture_output=True, text=True, timeout=10)
                print(f"[backend] Terminated existing backend tree (PID {pid}) on port {port}.")
        else:
            # POSIX: lsof first, then fuser as a fallback.
            res = subprocess.run(["lsof", "-ti", f"tcp:{port}"],
                                 capture_output=True, text=True, timeout=10)
            pids = [p for p in res.stdout.split() if p]
            if pids:
                subprocess.run(["kill", "-9", *pids], capture_output=True, text=True, timeout=10)
                print(f"[backend] Terminated existing backend (PIDs {', '.join(pids)}) on port {port}.")
            else:
                subprocess.run(["fuser", "-k", f"{port}/tcp"],
                               capture_output=True, text=True, timeout=10)
    except Exception as e:
        print(f"[warn] Could not terminate backend on port {port}: {type(e).__name__}: {e}")


def _wait_for_port_free(url: str, timeout: int = 15, interval: int = 1) -> bool:
    """Poll until `url` stops responding (the backend has shut down)."""
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=3)
            time.sleep(interval)
        except Exception:
            return True
    return False


def start_backend_if_needed(
    log_path: str,
    backend_flags: list[str] | None = None,
    restart: bool = False,
) -> subprocess.Popen | None:
    import urllib.request
    if backend_flags is None:
        backend_flags = []

    running = False
    try:
        urllib.request.urlopen("http://localhost:5002/health", timeout=3)
        running = True
    except Exception:
        running = False

    if running:
        if restart:
            # The caller explicitly asked to replace any existing backend so its
            # enrichment flags (e.g. --enrich-formula) actually take effect.
            print(
                f"[backend] --restart-backend: terminating existing backend on port 5002 "
                f"to apply flags ({' '.join(backend_flags) or 'none'})..."
            )
            _terminate_backend_on_port(5002)
            if not _wait_for_port_free("http://localhost:5002/health"):
                print(
                    "[warn] Existing backend on port 5002 is still responding after the "
                    "terminate attempt; starting a fresh one may fail."
                )
            # fall through to the start path below
        else:
            print("[backend] Already running on port 5002")
            if backend_flags:
                print(
                    f"[warn] Existing backend on port 5002 won't pick up enrichment flags "
                    f"({' '.join(backend_flags)}). Pass --restart-backend to replace it, kill it "
                    f"and re-run to enable, or pass --no-hybrid to skip the backend if "
                    f"enrichments aren't critical."
                )
            return None

    print("[backend] Starting hybrid backend...")
    with open(log_path, "w") as log_fh:
        proc = subprocess.Popen(
            ["opendataloader-pdf-hybrid", "--port", "5002", "--device", "auto"] + backend_flags,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
        )
    if not wait_for_health("http://localhost:5002/health"):
        print("[backend] ERROR: Backend did not become healthy within 90s")
        # Clean up the spawned backend before exiting so we don't leak a
        # long-running child. sys.exit() unwinds past main()'s try/finally
        # because backend_proc was never assigned there. Tree-kill (not a bare
        # terminate) so Docling's multiprocessing.spawn workers are reaped too —
        # on Windows, terminating only the parent orphans them.
        _terminate_proc_tree(proc)
        sys.exit(1)
    print("[backend] Healthy")
    return proc


def tail_log_for_progress(log_path: str, bar: tqdm, stop_event: threading.Event):
    """Tail the backend log and update the progress bar on page processing events."""
    seen_pages: set[int] = set()
    pattern = re.compile(r"pages \[(\d+)\]")

    while not stop_event.is_set():
        try:
            with open(log_path, "r") as f:
                for line in f:
                    for m in pattern.finditer(line):
                        pg = int(m.group(1))
                        if pg not in seen_pages:
                            seen_pages.add(pg)
                            bar.update(1)
        except FileNotFoundError:
            pass
        stop_event.wait(1.0)


def main():
    if "--selfcheck" in sys.argv:
        _selfcheck()
        return
    ap = argparse.ArgumentParser(description="Convert PDF to Markdown with progress bar")
    ap.add_argument("input_path", help="Path to the input PDF")
    ap.add_argument("--output-dir", "-o", default=None, help="Output directory (default: same as input)")
    ap.add_argument("--format", "-f", default="markdown", help="Output format (default: markdown)")
    ap.add_argument("--no-hybrid", dest="hybrid", action="store_false", help="Skip the hybrid backend and run local-only (default is hybrid ON).")
    ap.set_defaults(hybrid=True)
    ap.add_argument("--image-output", default="embedded", help="Image handling: off, embedded, external")
    ap.add_argument("--pages", default=None, help="Page range, e.g. '1-50'")
    ap.add_argument(
        "--probe-output",
        default=None,
        help="Path to probe_pdf.py JSON output; enables auto-derived enrichment flags",
    )
    ap.add_argument(
        "--keep-backend",
        action="store_true",
        default=False,
        help="Do not terminate the hybrid backend process after conversion (default: terminate).",
    )
    ap.add_argument(
        "--restart-backend",
        action="store_true",
        default=False,
        help="If a hybrid backend is already running, terminate and replace it so probe-derived "
             "enrichment flags (e.g. --enrich-formula for math→LaTeX) actually take effect. "
             "Without this, an existing backend is reused and the flags are silently dropped.",
    )
    ap.add_argument(
        "--no-clean-fragments",
        dest="clean_fragments",
        action="store_false",
        default=True,
        help="Do NOT strip garbled vector-figure text fragments from the Markdown after "
             "conversion (default: clean). Figures carry their labels in the PDF text layer; the "
             "parser crops the figure to an image but also leaks those labels as short garbled "
             "runs next to it. The cleanup removes them while protecting LaTeX, tables, and prose.",
    )
    ap.add_argument(
        "--no-sanitize-math",
        dest="sanitize_math",
        action="store_false",
        default=True,
        help="Do NOT make math KaTeX-safe after conversion (default: sanitize). Wraps leaked "
             "alignment (& / \\\\) in \\begin{aligned} and suppresses equation blocks the KaTeX "
             "engine cannot render, so a renderer never shows a parse-error string.",
    )
    args = ap.parse_args()

    input_path = Path(args.input_path).resolve()
    if not input_path.exists():
        print(f"ERROR: {input_path} does not exist")
        sys.exit(1)

    # Harden the third-party JAR runner against non-UTF-8 log bytes before it is
    # ever invoked (self-healing; survives pip upgrades). See the function docstring.
    ensure_runner_safe_decode()

    output_dir = args.output_dir or str(input_path.parent)
    total_pages = count_pages(str(input_path))
    print(f"[info] {input_path.name}: {total_pages} pages")

    progress_total = _progress_total_for_pages(args.pages, total_pages)
    if args.pages and progress_total == total_pages and not _SIMPLE_RANGE_RE.match(args.pages.strip()):
        # We accepted a complex --pages spec (e.g. "3,5,7-9") but couldn't
        # compute its subset count. Surface this so the bar isn't silently
        # misleading.
        print(
            f"[info] --pages={args.pages!r} format not recognized for subset accounting; "
            f"progress total reflects whole-document page count ({total_pages})."
        )

    _fd, log_path = tempfile.mkstemp(suffix=".log", prefix="odl_hybrid_")
    os.close(_fd)

    backend_flags = derive_backend_flags(args.probe_output)

    # Silent-ignore guard: probe-derived backend flags only take effect when the
    # hybrid backend actually runs. If the user disabled hybrid, surface this so
    # they don't silently lose --force-ocr / --enrich-formula behavior.
    if backend_flags and not args.hybrid:
        print(
            f"[warn] Probe derived backend flags ({' '.join(backend_flags)}) but "
            f"--no-hybrid was passed; the hybrid backend is the only consumer of "
            f"these flags, so they will have no effect. Drop --no-hybrid to enable."
        )

    backend_proc = None
    if args.hybrid:
        backend_proc = start_backend_if_needed(
            log_path, backend_flags, restart=args.restart_backend
        )

    # Build CLI command
    cmd = ["opendataloader-pdf"]
    if args.hybrid:
        cmd += ["--hybrid", "docling-fast"]
    cmd += [
        "--format", args.format,
        "--image-output", args.image_output,
        "-o", output_dir,
    ]
    if args.pages:
        cmd += ["--pages", args.pages]
    cmd.append(str(input_path))

    # Progress bar — tracks hybrid backend page events (complex pages only)
    # For fast mode or pages that don't hit the backend, the bar may not reach 100%
    bar = tqdm(
        total=progress_total,
        desc="Converting",
        unit="page",
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} pages [{elapsed}<{remaining}]",
    )

    stop_event = threading.Event()
    log_thread = threading.Thread(
        target=tail_log_for_progress, args=(log_path, bar, stop_event), daemon=True
    )
    log_thread.start()

    # Run the conversion — the CLI itself also outputs progress to stderr.
    # stdout is discarded (DEVNULL) to prevent the 64 KB Windows pipe-buffer
    # deadlock that arises when stdout=PIPE and the parent only reads it after wait().
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # Also parse the CLI's own stderr for page progress (lines like "Page 42/944")
        page_pattern = re.compile(r"(\d+)/(\d+)")
        last_page = 0

        for line in proc.stderr:
            decoded = line.decode("utf-8", errors="replace").strip()
            m = page_pattern.search(decoded)
            if m:
                current = int(m.group(1))
                if current > last_page:
                    bar.update(current - last_page)
                    last_page = current

        proc.wait()
        stop_event.set()

        # Ensure bar reaches total on success
        if proc.returncode == 0:
            bar.n = progress_total
            bar.refresh()
        bar.close()

        if proc.returncode == 0:
            stem = input_path.stem
            md_path = Path(output_dir) / f"{stem}.md"
            print(f"\n[done] Output: {md_path}")
            if "--enrich-formula" in backend_flags and args.hybrid:
                applied = backend_proc is not None or args.restart_backend
                if applied:
                    print(
                        "[done] Formula enrichment ON: equations should be emitted as LaTeX "
                        "($$...$$). Verify with the math checklist in extraction.md §formulas."
                    )
                else:
                    print(
                        "[warn] Formula enrichment was requested but a pre-existing backend was "
                        "reused, so --enrich-formula may NOT have applied. Re-run with "
                        "--restart-backend to guarantee LaTeX output."
                    )
            if args.clean_fragments and md_path.exists():
                clean_fragments_in_place(md_path)
            if args.sanitize_math and md_path.exists():
                sanitize_math_in_place(md_path)
            # Always gate the result — silent table/equation failures are the
            # common case on born-digital academic papers, so detection can't be
            # an optional step the operator might skip.
            if md_path.exists():
                run_quality_gate(md_path, args.probe_output)
        else:
            print(f"\n[error] Conversion failed (exit code {proc.returncode})")
            sys.exit(proc.returncode)
    finally:
        if backend_proc is not None and not args.keep_backend:
            # Tree-kill so Docling's multiprocessing.spawn workers are reaped too,
            # not just the backend parent (otherwise they orphan on Windows).
            _terminate_proc_tree(backend_proc)


if __name__ == "__main__":
    main()
