"""Extract reviewer annotations (comments, highlights, sticky notes) from a PDF,
each with the marked text and the surrounding paragraph as context.

Usage: python extract_annotations.py <input.pdf> [output.md]

Verified on co-author-annotated manuscript PDFs (2026-07). Key gotchas this
script already handles:
- hyperref-generated Link annotations (plus Popup/Widget) are excluded; without
  the filter an academic PDF yields hundreds of junk entries.
- Text under highlight quadpoints comes back noisy (stray glyphs from
  overlapping quads); it is still useful for locating the marked span, but the
  clean prose comes from the `context` field, which pulls full text blocks
  overlapping the annotation rect via page.get_text("blocks").
"""
import os
import sys
import fitz

SKIP = {"Link", "Popup", "Widget"}
MARKUP = ("Highlight", "Underline", "Squiggly", "StrikeOut")


def quad_text(page, annot):
    """Text under a markup annotation's quadpoints. Noisy but locates the span."""
    try:
        verts = annot.vertices
        if not verts:
            return ""
        pieces = []
        for i in range(0, len(verts), 4):
            quad = verts[i:i + 4]
            xs = [p[0] for p in quad]
            ys = [p[1] for p in quad]
            r = fitz.Rect(min(xs), min(ys), max(xs), max(ys))
            t = page.get_text("text", clip=r).strip()
            if t:
                pieces.append(t)
        return " ".join(pieces).replace("\n", " ")
    except Exception:
        return ""


def context_block(page, rect, pad=25):
    """Full text blocks overlapping the annotation rect (± pad vertically)."""
    zone = fitz.Rect(0, rect.y0 - pad, page.rect.width, rect.y1 + pad)
    out = []
    for b in page.get_text("blocks"):
        br = fitz.Rect(b[:4])
        if br.intersects(zone) and b[4].strip():
            out.append(" ".join(b[4].split()))
    return "\n\n".join(out)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    pdf = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(pdf)[0] + "_annotations.md"

    doc = fitz.open(pdf)
    entries = []
    for page in doc:
        for annot in page.annots() or []:
            subtype = annot.type[1]
            if subtype in SKIP:
                continue
            info = annot.info
            entries.append({
                "page": page.number + 1,
                "type": subtype,
                "author": info.get("title", ""),
                "comment": (info.get("content") or "").strip(),
                "anchor": quad_text(page, annot) if subtype in MARKUP else "",
                "context": context_block(page, annot.rect),
            })

    lines = [f"# Annotations — {os.path.basename(pdf)}",
             f"\n{len(entries)} annotations (Link/Popup/Widget excluded).\n"]
    for i, e in enumerate(entries, 1):
        lines.append(f"\n---\n\n## {i}. p.{e['page']} — {e['type']}"
                     + (f" ({e['author']})" if e['author'] else ""))
        if e["anchor"]:
            lines.append(f"\n**Marked text:** {e['anchor']}")
        lines.append(f"\n**Comment:** {e['comment'] or '*(none — mark only)*'}")
        if e["context"]:
            lines.append("\n**Context:**\n\n> " + e["context"].replace("\n\n", "\n>\n> "))

    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{len(entries)} annotations -> {out}")


if __name__ == "__main__":
    main()
