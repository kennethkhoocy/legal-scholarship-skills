"""Convert intermediate/*.tex to output/*.docx using pandoc."""

import subprocess
import sys
import os
import re
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def count_footnotes(tex_path):
    with open(tex_path, encoding="utf-8") as f:
        text = f.read()
    return len(re.findall(r"\\footnote\{", text)), len(text.splitlines())


def footnote_style_size(docx_path):
    """Half-point size of the output's Footnote Text style, or None if unset
    (unset means footnotes inherit the full body size)."""
    with zipfile.ZipFile(docx_path) as z:
        styles = z.read("word/styles.xml").decode("utf-8")
    style = re.search(
        r'<w:style[^>]*w:styleId="FootnoteText"[^>]*>.*?</w:style>', styles, re.S
    )
    if style is None:
        return None
    sz = re.search(r'<w:sz w:val="(\d+)"', style.group(0))
    return int(sz.group(1)) if sz else None


def sanity_check(tex_path, docx_path):
    orig_fn, orig_lines = count_footnotes(tex_path)

    # Round-trip: convert output docx back to tex for comparison
    tmp = os.path.join(tempfile.gettempdir(), "roundtrip_check.tex")
    subprocess.run(
        ["pandoc", docx_path, "-t", "latex", "-o", tmp],
        check=True,
    )
    rt_fn, rt_lines = count_footnotes(tmp)

    # Preview first 3 footnotes from the original tex
    with open(tex_path, encoding="utf-8") as f:
        text = f.read()
    previews = re.findall(r"\\footnote\{([^}]{0,80})", text)[:3]

    print(f"\n=== Conversion Summary ===")
    print(f"Original .tex — Lines: {orig_lines:,}  Footnotes: {orig_fn}")
    print(f"Round-trip .tex — Lines: {rt_lines:,}  Footnotes: {rt_fn}")
    if previews:
        print("First 3 footnotes (from original .tex):")
        for p in previews:
            print(f"  \\footnote{{{p}...}}" if len(p) == 80 else f"  \\footnote{{{p}}}")

    if orig_fn != rt_fn:
        print(f"\nWARNING: Footnote count mismatch ({orig_fn} vs {rt_fn}) — inspect before delivering.")
    else:
        print("\nFootnote counts match.")

    sz = footnote_style_size(docx_path)
    if sz:
        print(f"Footnote Text style size: {sz / 2:g}pt")
    else:
        print("WARNING: Footnote Text style has no explicit size — footnotes "
              "will render at body size. Rebuild reference.docx with gen_reference.py.")


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/tex_to_docx.py v1")
        sys.exit(1)

    version = sys.argv[1]
    input_path = os.path.join(ROOT, "intermediate", f"intermediate_{version}.tex")
    output_path = os.path.join(ROOT, "output", f"output_{version}.docx")
    # Resolve next to this script so it works both in the skill tree and when
    # the scripts/ folder is copied into a project.
    reference = os.path.join(SCRIPT_DIR, "reference.docx")

    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found")
        sys.exit(1)

    if not os.path.exists(reference):
        # Pandoc's default styles give Footnote Text no size, so footnotes
        # would render at full body size. Refuse rather than deliver that.
        print(f"Error: {reference} not found — pandoc defaults render footnotes "
              f"at body size. Copy the skill's scripts/reference.docx next to this "
              f"script, or regenerate it with: python {os.path.join(SCRIPT_DIR, 'gen_reference.py')} "
              f"(needs the full scripts/ folder, including toolcheck.py)")
        sys.exit(1)

    os.makedirs(os.path.join(ROOT, "output"), exist_ok=True)

    cmd = [
        "pandoc", input_path,
        "-f", "latex",
        "-o", output_path,
        f"--reference-doc={reference}",
    ]

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"Created: {output_path}")

    sanity_check(input_path, output_path)


if __name__ == "__main__":
    main()
