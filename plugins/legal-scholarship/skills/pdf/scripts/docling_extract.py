"""Footnote- and formula-aware Markdown extraction via Docling (direct).

opendataloader-pdf discards Docling's footnote labels and jumbles the footnote
text into the body. Calling Docling directly preserves both the footnote
definitions (each as a labelled item beginning with its `N` / `*` marker) and
the in-body reference markers, so footnotes can be reconstructed as proper
Markdown:

    ... the IPO documents.[^1] After ...
    ...
    [^1]: See Atkins (2018) and Graf (2018).

Docling also produces formula LaTeX (`do_formula_enrichment`), so this path is
the right one for born-digital academic papers (footnotes + equations). The
output still goes through the skill's KaTeX-sanitize pass.

Usage:
    python docling_extract.py <input.pdf> [-o out.md] [--pages A-B] [--no-formula]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Abbreviated cross-references — the period belongs to the abbreviation, so a
# number after "p.", "fig.", "no." is a reference, not a footnote marker.
_REF_ABBREV_BEFORE = re.compile(
    # Word abbreviations carry the period ("p.", "fig.", "no."); the section
    # sign is a separate branch because "\b" cannot anchor before the non-word
    # "§", so "§ 12" would otherwise slip through and 12 be taken as a marker.
    r"(?:\b(?:pp?|fig|figs|no|nos|art|arts|ch|chs|vol|vols|sec|secs|tbl|eq|eqn|ed)\.?\s*|§+\s*)$",
    re.IGNORECASE,
)
# Spelled-out cross-references ("Section 4", "Appendix B"). Matched only when the
# number follows directly (no sentence-ending period): "the note. 12" ends a
# sentence, so 12 IS a footnote marker and must not be rejected here.
_REF_WORD_BEFORE = re.compile(
    r"\b(?:section|sections|appendix|appendices|figure|figures|table|tables|"
    r"chapter|chapters|equation|equations|lemma|proposition|propositions|"
    r"theorem|corollary|part|parts|article|articles|paragraph|para|note|notes|"
    r"item|items|rule|rules|clause|step|case|column|col|row|exhibit|schedule|"
    r"line|version|volume|page|pages)\s+$",
    re.IGNORECASE,
)
# Units / suffixes that mean a preceding number is a quantity, not a marker.
_UNIT_AFTER = re.compile(
    r"^\s*(?:%|percent|per\s?cent|million|billion|trillion|thousand|bn|mn|k|"
    r"basis|bps|years?|yrs?|months?|weeks?|days?|hours?|hrs?|minutes?|mins?|"
    r"am|pm|st|nd|rd|th|cents?|dollars?)\b",
    re.IGNORECASE,
)

# How many consecutive footnote numbers may be absent from the body text (e.g. a
# reference that lives only inside a figure) before a later candidate is treated
# as a spurious match rather than a resumption of the sequence.
_MARKER_SKIP_TOLERANCE = 12

# When a page range starts mid-note, the first FOOTNOTE item Docling emits can be
# a citation continuation ("93 YALE L.J. 1073 (1984).") rather than a real note
# start. A continuation is the tail of a citation: <volume> <reporter> <page>,
# e.g. "93 YALE L.J. 1073" or "318 U.S. 80". Requiring the trailing page number
# is what keeps the guard from demoting genuine legal first notes that merely
# open with an abbreviation or acronym ("1 SEC v. Chenery…", "37 Id. at…",
# "37 Cf. Smith…"). When matched at bootstrap the fragment falls through to the
# unlabeled path (→ endnotes, text preserved) instead of minting a phantom note.
_CITATION_CONT_RE = re.compile(r"^\s*\d{1,3}\s+(?:[A-Z][A-Za-z.0-9]*\.?\s+){1,3}\d{1,4}")


def convert(pdf_path: str, page_range: tuple[int, int] | None = None,
            formula: bool = True, images: bool = True):
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    opts = PdfPipelineOptions()
    opts.do_ocr = False
    opts.do_formula_enrichment = formula
    if images:
        # Rasterise figure regions so they can be embedded/exported.
        opts.generate_picture_images = True
        opts.images_scale = 2.0
    conv = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    kwargs = {}
    if page_range:
        kwargs["page_range"] = page_range
    return conv.convert(pdf_path, **kwargs).document


def _heading(level, text: str) -> str:
    lvl = level if isinstance(level, int) and level >= 1 else 1
    return "#" * min(lvl + 1, 6) + " " + text.strip()


def _picture_markdown(it, doc, mode: str, images_dir, idx: int) -> str:
    """Markdown for a figure: an embedded base64 image by default (so the figure
    lives inside the .md), an external file reference, or a placeholder."""
    cap = ""
    try:
        cap = (it.caption_text(doc) or "").strip()
    except Exception:
        cap = ""
    img_tag = ""
    if mode != "none":
        pil = None
        try:
            pil = it.get_image(doc)
        except Exception:
            pil = None
        if pil is not None:
            import base64
            import io
            if mode == "external" and images_dir is not None:
                images_dir.mkdir(parents=True, exist_ok=True)
                path = images_dir / f"figure_{idx}.png"
                pil.save(str(path), format="PNG")
                img_tag = f"![figure {idx}]({images_dir.name}/{path.name})"
            else:  # embedded — image bytes inside the Markdown
                buf = io.BytesIO()
                pil.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                img_tag = f"![figure {idx}](data:image/png;base64,{b64})"
    parts = [p for p in (img_tag, cap) if p]
    return "\n\n".join(parts) if parts else "<!-- figure -->"


def collect(doc, image_mode: str = "embedded", images_dir=None) -> tuple[list[str], list[tuple[str, str]]]:
    """Return (body_blocks, footnotes) where footnotes is a list of (label, text).

    Footnotes are pulled out of the reading-order stream so the body flows
    continuously; they are re-emitted as definitions at the end. Figures are
    embedded (base64), exported, or left as placeholders per `image_mode`.
    """
    body: list[str] = []
    footnotes: list = []
    pic_idx = 0
    last_num = 0  # highest footnote number started so far (for sequence checks)
    for it, level in doc.iterate_items():
        label = str(getattr(it, "label", "")).lower()
        text = (getattr(it, "text", "") or "").strip()
        if label.endswith("footnote"):
            sym = re.match(r"^\s*([∗*†‡§])\s+(.*)$", text, re.DOTALL)
            num = re.match(r"^\s*(\d{1,3})[.\):]?\s+(.*)$", text, re.DOTALL)
            if sym:
                footnotes.append([sym.group(1), sym.group(2).strip()])
            elif (num and (last_num == 0 or last_num < int(num.group(1)) <= last_num + 20)
                  and not (last_num == 0 and _CITATION_CONT_RE.match(text))):
                # A plausible *next* footnote number starts a new note. The first
                # numeric note always bootstraps the sequence (last_num == 0) so a
                # page-range extraction beginning mid-document — where the first
                # footnote may be numbered far above 20 — still captures its label
                # instead of degrading the whole range to empty markers. Once the
                # sequence has begun, an out-of-window number (e.g. a citation
                # volume like "93 YALE L.J.") is a continuation, not a new note.
                last_num = int(num.group(1))
                footnotes.append([num.group(1), num.group(2).strip()])
            elif text and footnotes:
                # A fragment with no (plausible) number — Docling split a long
                # note (common in law reviews). Append it to the note it
                # continues so each footnote stays a single, delimited entry.
                footnotes[-1][1] = (footnotes[-1][1] + " " + text).strip()
            elif text:
                footnotes.append(["", text])
            continue
        if not text and not label.endswith(("table", "picture")):
            continue
        if label.endswith(("page_header", "page_footer")):
            continue
        if label.endswith(("title", "section_header")):
            body.append(_heading(1 if label.endswith("title") else level, text))
        elif label.endswith("formula"):
            body.append("$$\n" + text + "\n$$")
        elif label.endswith("table"):
            try:
                body.append(it.export_to_markdown(doc).strip())
            except Exception:
                if text:
                    body.append(text)
        elif label.endswith("picture"):
            pic_idx += 1
            body.append(_picture_markdown(it, doc, image_mode, images_dir, pic_idx))
        else:  # text, list_item, caption, code, ...
            body.append(text)
    return body, [tuple(f) for f in footnotes]


_MONTH_BEFORE = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\b\.?\s+$",
    re.IGNORECASE,
)


def _is_marker_context(s: str, start: int, end: int) -> bool:
    """True if the digit run s[start:end] looks like a footnote reference marker
    rather than a cross-reference, date, year, or quantity."""
    before = s[max(0, start - 24):start]
    after = s[end:end + 16]
    if before[-1:].isdigit() or after[:1].isdigit():
        return False  # part of a larger number (e.g. a year, "421")
    if re.search(r"[$£€]\s*$", before):
        return False  # "$ 13" — a monetary amount, not a marker
    if _REF_ABBREV_BEFORE.search(before) or _REF_WORD_BEFORE.search(before):
        return False  # "Section 4", "Appendix 2", "p. 5", ...
    if _UNIT_AFTER.match(after):
        return False  # "5 percent", "10 million", ...
    if re.match(r"^\s*,\s*\d{3,4}\b", after) or _MONTH_BEFORE.search(before):
        return False  # a date: "October 7, 2021"
    # Not inside a heading ("## 2 Literature Review") or a table row.
    line_start = s.rfind("\n", 0, start) + 1
    lead = s[line_start:start].lstrip()
    if lead.startswith("#") or lead.startswith("|"):
        return False
    # Not the opener of a numbered list ("1. First", "2) Second") — Docling can
    # emit list numbers as literal body text. Reject the leading number itself,
    # but a genuine marker later on the same line (e.g. "1. The firm disclosed.5")
    # is left untouched because then `lead` is non-empty.
    if not lead and re.match(r"^\d{1,3}[.)]\s", s[start:start + 5]):
        return False
    # Markers are set off: immediately preceded by whitespace, an opening
    # bracket, or sentence punctuation (Docling keeps them space-padded).
    prev = s[start - 1] if start > 0 else " "
    if not (prev.isspace() or prev in "([.)]”\"’"):
        return False
    return True


def _escape_inline(text: str) -> str:
    """Make footnote text safe inside a pandoc inline footnote `^[ ... ]` by
    escaping the brackets (and backslash) so they don't terminate the note."""
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def link_markers(body_md: str, footnotes: list[tuple[str, str]]) -> tuple[str, list[int]]:
    """Convert in-body reference markers to [^n].

    Two passes so a single spurious candidate cannot derail the rest:
      1. Gather every digit run that is a known footnote number and passes the
         marker-context filter (excludes cross-references, years, quantities).
      2. Walk the candidates in document order and accept one only when its
         footnote-number index advances the sequence by at most
         `_MARKER_SKIP_TOLERANCE` — tolerating markers genuinely absent from the
         text while rejecting out-of-sequence false matches.
    Replacements are applied right-to-left so earlier offsets stay valid.
    Returns (markdown, sorted_list_of_linked_numbers).
    """
    nums = sorted({int(lbl) for lbl, _ in footnotes if lbl.isdigit()})
    if not nums:
        return body_md, []
    numset = set(nums)
    idx_of = {n: i for i, n in enumerate(nums)}

    candidates: list[tuple[int, int, int]] = []
    for m in re.finditer(r"\d{1,3}", body_md):
        v = int(m.group())
        if v in numset and _is_marker_context(body_md, m.start(), m.end()):
            candidates.append((m.start(), m.end(), v))

    # Pass 1 — greedy, in document order, robust to false high-number candidates.
    chosen: dict[int, tuple[int, int]] = {}
    used: set[int] = set()
    expect = 0
    for st, en, v in candidates:
        j = idx_of[v]
        if v not in chosen and j >= expect and (j - expect) <= _MARKER_SKIP_TOLERANCE:
            chosen[v] = (st, en)
            used.add(st)
            expect = j + 1

    # Pass 2 — recover footnotes still unlinked from a *unique* remaining
    # candidate. This catches markers that appear out of reading order
    # (multi-column layout) which the in-order pass skipped, without risking a
    # false link (only an unambiguous single candidate is accepted).
    remaining: dict[int, list[tuple[int, int]]] = {}
    for st, en, v in candidates:
        if v not in chosen and st not in used:
            remaining.setdefault(v, []).append((st, en))
    for v, occ in remaining.items():
        if len(occ) == 1:
            chosen[v] = occ[0]

    # Replace each located marker with an inline footnote carrying the note text,
    # right at the reference point (e.g. `documents.^[See Atkins (2018).]`), so
    # the note's start (`^[`) and end (`]`) are unambiguous in the raw Markdown.
    text_by = {int(l): t for l, t in footnotes if str(l).isdigit()}
    s = body_md
    linked: list[int] = []
    for v, (st, en) in sorted(chosen.items(), key=lambda x: -x[1][0]):
        pre = st - 1 if (st > 0 and s[st - 1].isspace()) else st
        s = s[:pre] + "^[" + _escape_inline(text_by[v]) + "]" + s[en:]
        linked.append(v)
    return s, sorted(linked)


def render_endnotes(footnotes: list[tuple[str, str]]) -> str:
    # Footnotes whose in-text reference marker could not be located (e.g.
    # absorbed into an equation, or in a region Docling did not extract as
    # prose). They have no reference point to inline at, so they are listed by
    # original number as plain text — preserved through pandoc instead of being
    # dropped (a bare `[^n]:` with no reference is deleted by pandoc).
    lines = [
        "## Endnotes",
        "",
        "<!-- Footnotes whose in-text marker could not be located; preserved here "
        "by original number so no content is lost in conversion. -->",
        "",
    ]
    numeric = sorted(((l, t) for l, t in footnotes if str(l).isdigit()), key=lambda x: int(x[0]))
    for lbl, t in numeric:
        lines.append(f"**[{int(lbl)}]** {t}")
        lines.append("")
    for lbl, t in (f for f in footnotes if not str(f[0]).isdigit()):
        label = lbl if str(lbl).strip() else "note"
        lines.append(f"**[{label}]** {t}")
        lines.append("")
    return "\n".join(lines).rstrip()


_SYMBOL_GLYPHS = "∗*†‡§"


def _symbol_variants(label: str) -> list:
    # A blank/whitespace label has no symbol to locate — it belongs in the
    # endnotes, not attached to a stray glyph. Guard against `"" in "*∗"` being
    # true, which would otherwise hand a blank label the star variants and let it
    # latch onto an italic delimiter.
    if not label.strip():
        return []
    # Docling may emit the acknowledgment star as ASCII '*' or the operator '∗';
    # treat them interchangeably so the note is found regardless of glyph.
    return ["∗", "*"] if label in ("*", "∗") else [label]


def _is_symbol_marker(s: str, start: int, end: int, symbol: str) -> bool:
    """True if the symbol at s[start:end] is set off as a footnote reference
    marker rather than Markdown syntax or a statute reference.

    The star is the only ambiguous glyph (Markdown uses it for bullets and
    emphasis), so it keeps the conservative original rule: trailed by whitespace
    or line end, and not a bullet or emphasis delimiter. Daggers and the section
    sign are never Markdown syntax, so they are accepted wherever they sit,
    except "§ 12" which is a statute reference.
    """
    prev = s[start - 1] if start > 0 else "\n"
    nxt = s[end] if end < len(s) else ""
    if symbol in ("*", "∗"):
        line_start = s.rfind("\n", 0, start) + 1
        if s[line_start:start].strip() == "" and (nxt == "" or nxt.isspace()):
            return False  # a lone "* " at line start is a Markdown bullet
        if prev == "*" or nxt == "*":
            return False  # adjacent stars: **bold**
        if not (nxt == "" or nxt.isspace()):
            return False  # a real marker is trailed by whitespace or line end
        # A star that closes an emphasis span — an odd number of star glyphs
        # precede it on the line — is Markdown italics (*italic*), not a marker.
        if (s[line_start:start].count("*") + s[line_start:start].count("∗")) % 2 == 1:
            return False
        return True
    if symbol == "§" and re.match(r"\s*\d", s[end:end + 4]):
        return False  # "§ 12" — a statute reference, not a footnote marker
    return True


def _inline_symbol_notes(body_md: str, symbol_notes: list) -> tuple:
    """Inline each symbol footnote at its first valid in-body marker.

    Returns (rewritten_body, set_of_inlined_indices). A note with no locatable
    marker is left for the caller to route to the endnotes section with its
    symbol label intact. Replacements are gathered against the original offsets
    and applied right-to-left so earlier positions stay valid.
    """
    occupied: list = []
    edits: list = []
    inlined: set = set()
    for i, (label, text) in enumerate(symbol_notes):
        spot = None
        for var in _symbol_variants(label):
            for m in re.finditer(re.escape(var), body_md):
                st, en = m.start(), m.end()
                if any(st < oe and ost < en for ost, oe in occupied):
                    continue  # this glyph is already an inlined marker
                if _is_symbol_marker(body_md, st, en, var):
                    spot = (st, en)
                    break
            if spot:
                break
        if spot:
            st, en = spot
            occupied.append((st, en))
            edits.append((st, en, "^[" + _escape_inline(text) + "]"))
            inlined.add(i)
    for st, en, rep in sorted(edits, key=lambda x: -x[0]):
        body_md = body_md[:st] + rep + body_md[en:]
    return body_md, inlined


def build_markdown(doc, image_mode: str = "embedded", images_dir=None) -> tuple[str, dict]:
    body, footnotes = collect(doc, image_mode=image_mode, images_dir=images_dir)
    body_md = "\n\n".join(b for b in body if b)
    # Linked footnotes are inlined into the body at their reference point.
    body_md, linked = link_markers(body_md, footnotes)
    linked_set = set(linked)

    # Inline every symbol note (∗ * † ‡ §) at its in-body marker — not only the
    # first acknowledgment star — so daggers and section signs keep their
    # reference point instead of falling to generic endnotes.
    symbol_notes = [(l, t) for l, t in footnotes if not str(l).isdigit()]
    inlined_idx: set = set()
    if symbol_notes:
        body_md, inlined_idx = _inline_symbol_notes(body_md, symbol_notes)

    numeric_numbers = sorted({int(l) for l, _ in footnotes if str(l).isdigit()})
    text_by = {int(l): t for l, t in footnotes if str(l).isdigit()}
    # Footnotes whose marker could not be located (or symbol notes with no marker
    # in the body) → endnotes, so nothing is dropped on the way to .tex.
    endnotes = [(str(n), text_by[n]) for n in numeric_numbers if n not in linked_set]
    endnotes += [sn for i, sn in enumerate(symbol_notes) if i not in inlined_idx]

    report = {
        "footnotes": len(numeric_numbers),
        "markers_linked": len(linked),
        "unlinked": sorted(set(numeric_numbers) - linked_set),
        "endnotes": sum(1 for l, _ in endnotes if str(l).isdigit()),
        "has_ack": bool(symbol_notes),
    }
    md = body_md.rstrip()
    if endnotes:
        md = md + "\n\n" + render_endnotes(endnotes) + "\n"
    return md, report


def _parse_pages(s: str | None):
    if not s:
        return None
    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", s)
    if not m:
        raise ValueError(f"--pages must be 'A-B', got {s!r}")
    return (int(m.group(1)), int(m.group(2)))


def main() -> None:
    ap = argparse.ArgumentParser(description="Docling-direct footnote/formula-aware Markdown extraction.")
    ap.add_argument("input_path")
    ap.add_argument("-o", "--output", default=None)
    ap.add_argument("--pages", default=None, help="Page range 'A-B' (1-based)")
    ap.add_argument("--no-formula", dest="formula", action="store_false", default=True)
    ap.add_argument(
        "--image-output", default="embedded", choices=["embedded", "external", "none"],
        help="How figures appear: 'embedded' = base64 inside the .md (default, self-contained), "
             "'external' = saved to <stem>_images/ and referenced, 'none' = placeholder only.",
    )
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args()

    pdf = Path(args.input_path)
    if not pdf.exists():
        print(f"ERROR: {pdf} does not exist", file=sys.stderr)
        sys.exit(1)

    out = Path(args.output) if args.output else pdf.with_suffix(".md")
    images_dir = out.parent / f"{out.stem}_images" if args.image_output == "external" else None

    doc = convert(str(pdf), _parse_pages(args.pages), args.formula, images=args.image_output != "none")
    md, report = build_markdown(doc, image_mode=args.image_output, images_dir=images_dir)

    if not args.quiet:
        print(f"[docling] footnotes={report['footnotes']} markers_linked={report['markers_linked']} "
              f"endnotes={report['endnotes']} ack={report['has_ack']}", file=sys.stderr)

    out.write_text(md, encoding="utf-8")
    if not args.quiet:
        print(f"[docling] wrote {out}", file=sys.stderr)

    # Gate the result — the same silent table/equation failures apply on this
    # path. Best-effort; never breaks a successful extraction.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import verify_extraction as ve
        issues = ve.verify(md, formula_density=None)
        if issues:
            kinds: dict = {}
            for it in issues:
                kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
            summary = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
            print(f"[verify] {len(issues)} issue(s) to fix: {summary} — run "
                  f"verify_extraction.py '{out}' for line numbers; merged tables or broken equations → "
                  f"render the region with render_region.py and rewrite that block from the image (§4C).",
                  file=sys.stderr)
        else:
            print("[verify] clean — no merged tables, broken equations, or stray glyphs.", file=sys.stderr)
    except Exception as e:
        print(f"[warn] quality gate skipped: {type(e).__name__}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
