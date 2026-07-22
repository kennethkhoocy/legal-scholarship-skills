r"""Make extracted Markdown math KaTeX-safe.

Docling's formula model sometimes emits the *body* of a multi-line aligned
equation — with alignment markers ``&`` and row breaks ``\\`` — but WITHOUT the
``\begin{aligned} ... \end{aligned}`` wrapper. KaTeX permits ``&`` only inside an
environment, so rendering such a block throws, e.g.:

    KaTeX parse error: Expected 'EOF', got '&' at position 73: ... = & \frac { ( 1 - ...

It also occasionally splices prose or undefined macros (``\intertext``,
``\Deltad``) into a block, or leaves a stray ``\`` fragment — all of which throw.

This module rewrites each ``$$ ... $$`` block so that no parse error reaches a
downstream KaTeX renderer:

  1. A block with a *top-level* ``&`` / ``\\`` (not already inside a permitting
     environment) is wrapped in ``\begin{aligned} ... \end{aligned}`` — the
     equation is preserved and now renders.
  2. The result is validated with the real KaTeX engine when available. A block
     that still fails (undefined macro, spliced prose, stray ``\``) is suppressed
     — the ``$$ ... $$`` is removed. Suppression therefore happens only on a
     genuine parse error, never on a block KaTeX can render.

When KaTeX is not reachable, the module falls back to the lossless wrap plus a
conservative removal of obvious debris (empty / lone ``\``), and reports that it
ran in degraded (heuristic) mode.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Environments in which '&' / '\\' are already legal.
_PERMITTING = (
    r"cases|aligned|align|alignat|alignedat|array|matrix|[pbBvV]matrix|"
    r"smallmatrix|split|gathered|gather|multline|eqnarray|subarray|"
    r"CD|darray|dcases|rcases"
)
_ENV_SPAN = re.compile(r"\\begin\{(" + _PERMITTING + r")\}.*?\\end\{\1\}", re.DOTALL)
_BLOCK = re.compile(r"\$\$\n(.*?)\n\$\$", re.DOTALL)


# --- LaTeX helpers ------------------------------------------------------------

def _strip_envs(latex: str) -> str:
    prev = None
    cur = latex
    while prev != cur:
        prev = cur
        cur = _ENV_SPAN.sub("", cur)
    return cur


def _has_top_level_alignment(latex: str) -> bool:
    top = _strip_envs(latex).replace(r"\&", "")
    return ("&" in top) or bool(re.search(r"\\\\", top))


def _wrap_aligned(latex: str) -> str:
    body = latex.strip()
    body = re.sub(r"^(?:\\\\\s*)+", "", body)
    body = re.sub(r"(?:\\\\\s*)+$", "", body)
    return r"\begin{aligned} " + body + r" \end{aligned}"


def _is_obvious_debris(latex: str) -> bool:
    """Only the cases KaTeX is guaranteed to reject — used in fallback mode."""
    s = latex.strip()
    return s in ("", "\\", "\\\\")


# --- KaTeX validation oracle --------------------------------------------------

class KaTeXValidator:
    """Batch-validate LaTeX with the real KaTeX engine via Node.

    KaTeX is located from (in order):
      1. the single-file bundle vendored with the skill
         (scripts/vendor/katex.min.js) — ships and syncs with the skill, so the
         validator works on every machine that has Node, with no install and no
         `node_modules` in a synced config folder;
      2. the PDF_SKILL_KATEX env var (explicit override);
      3. a machine-local cache;
      4. a one-time npm install into that cache (last-resort fallback).
    If none resolve (e.g. Node absent), `available` is False and the sanitizer
    falls back to the lossless heuristic wrap.
    """

    def __init__(self, auto_install: bool = True):
        self._node = shutil.which("node")
        self._script = str(Path(__file__).resolve().parent / "katex_validate.js")
        self._katex = self._locate(auto_install)

    @property
    def available(self) -> bool:
        return bool(self._node and self._katex and os.path.exists(self._script))

    def _cache_dir(self) -> Path:
        base = (
            os.environ.get("LOCALAPPDATA")
            or os.environ.get("XDG_CACHE_HOME")
            or os.path.expanduser("~/.cache")
        )
        return Path(base) / "claude-pdf-skill-katex"

    def _locate(self, auto_install: bool):
        # 1. Vendored single-file bundle that ships with the skill (cross-machine).
        vendor = Path(__file__).resolve().parent / "vendor"
        for cand in (vendor / "katex.min.js", vendor / "katex.js"):
            if cand.exists():
                return str(cand)
        # 2. Explicit override.
        env = os.environ.get("PDF_SKILL_KATEX")
        if env and os.path.exists(env):
            return env
        # 3. Machine-local cache.
        cache = self._cache_dir() / "node_modules" / "katex"
        if cache.exists():
            return str(cache)
        # 4. One-time npm install into the local cache (last resort).
        if auto_install and self._node and (shutil.which("npm") or shutil.which("npm.cmd")):
            try:
                d = self._cache_dir()
                d.mkdir(parents=True, exist_ok=True)
                win = os.name == "nt"
                subprocess.run("npm init -y", cwd=str(d), shell=win,
                               capture_output=True, timeout=90)
                subprocess.run("npm install katex --no-audit --no-fund --silent",
                               cwd=str(d), shell=win, capture_output=True, timeout=240)
                if cache.exists():
                    return str(cache)
            except Exception:
                return None
        return None

    def validate_batch(self, items: list[str]):
        """Return list[bool] (True = renders). Returns None on validator failure."""
        if not items:
            return []
        if not self.available:
            return None
        fd, path = tempfile.mkstemp(suffix=".json", prefix="katex_in_")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(items, f)
            res = subprocess.run(
                [self._node, self._script, self._katex, path],
                capture_output=True, text=True, timeout=180,
            )
            if res.returncode != 0:
                return None
            out = json.loads(res.stdout)
            return out if isinstance(out, list) and len(out) == len(items) else None
        except Exception:
            return None
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


# --- core ---------------------------------------------------------------------

def sanitize(text: str, validator: "KaTeXValidator | None" = None) -> tuple[str, dict]:
    report = {"mode": "heuristic", "wrapped": 0, "suppressed": 0, "kept": 0, "details": []}
    matches = list(_BLOCK.finditer(text))
    if not matches:
        return text, report

    inners = [m.group(1) for m in matches]
    candidates = [
        _wrap_aligned(s) if _has_top_level_alignment(s) else s for s in inners
    ]
    wrapped_flag = [c != s for c, s in zip(candidates, inners)]

    # decision[i] = (action, content) where action in {"keep", "suppress"}
    decisions: list[tuple[str, str | None]] = []

    cand_ok = validator.validate_batch(candidates) if validator else None
    if cand_ok is not None:
        report["mode"] = "katex"
        # For candidates that fail, see whether the *original* renders (i.e. our
        # wrap broke something that was otherwise fine).
        need_orig = [i for i, ok in enumerate(cand_ok) if not ok]
        orig_ok_map: dict[int, bool] = {}
        if need_orig:
            res = validator.validate_batch([inners[i] for i in need_orig])
            if res is not None:
                orig_ok_map = {i: res[k] for k, i in enumerate(need_orig)}
        for i in range(len(inners)):
            if cand_ok[i]:
                decisions.append(("keep", candidates[i]))
            elif orig_ok_map.get(i, False):
                decisions.append(("keep", inners[i]))
            else:
                decisions.append(("suppress", None))
    else:
        # Fallback: lossless wrap; suppress only obvious debris.
        for i in range(len(inners)):
            if _is_obvious_debris(inners[i]):
                decisions.append(("suppress", None))
            else:
                decisions.append(("keep", candidates[i]))

    pieces: list[str] = []
    last = 0
    for m, (action, content), inner, was_wrapped in zip(matches, decisions, inners, wrapped_flag):
        pieces.append(text[last:m.start()])
        if action == "suppress":
            report["suppressed"] += 1
            report["details"].append(("suppressed", inner.strip()[:70]))
        else:
            pieces.append("$$\n" + content + "\n$$")
            if was_wrapped and content != inner:
                report["wrapped"] += 1
                report["details"].append(("wrapped", inner.strip()[:70]))
            else:
                report["kept"] += 1
        last = m.end()
    pieces.append(text[last:])

    result = re.sub(r"\n{3,}", "\n\n", "".join(pieces))
    return result, report


def main() -> None:
    ap = argparse.ArgumentParser(description="Make Markdown math KaTeX-safe (wrap alignment, suppress parse failures).")
    ap.add_argument("input_path", help="Markdown file to sanitize")
    ap.add_argument("-o", "--output", default=None, help="Write output here (default: stdout)")
    ap.add_argument("--in-place", action="store_true", help="Overwrite the input file")
    ap.add_argument("--dry-run", action="store_true", help="Report only; write nothing")
    ap.add_argument("--no-katex", action="store_true", help="Skip KaTeX validation (heuristic fallback only)")
    ap.add_argument("--no-install", action="store_true", help="Do not auto-install KaTeX if missing")
    ap.add_argument("-q", "--quiet", action="store_true", help="Suppress the report on stderr")
    args = ap.parse_args()

    path = Path(args.input_path)
    if not path.exists():
        print(f"ERROR: {path} does not exist", file=sys.stderr)
        sys.exit(1)

    validator = None if args.no_katex else KaTeXValidator(auto_install=not args.no_install)
    text = path.read_text(encoding="utf-8")
    out, report = sanitize(text, validator)

    if not args.quiet:
        print(
            f"[math] mode={report['mode']} | wrapped {report['wrapped']} alignment block(s), "
            f"suppressed {report['suppressed']} unparseable block(s), kept {report['kept']}",
            file=sys.stderr,
        )
        for kind, sample in report["details"]:
            print(f"  {kind}: {sample}", file=sys.stderr)

    if args.dry_run:
        return
    if args.in_place:
        path.write_text(out, encoding="utf-8")
    elif args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
