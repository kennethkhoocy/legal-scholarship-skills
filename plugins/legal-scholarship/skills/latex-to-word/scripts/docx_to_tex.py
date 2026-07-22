"""Convert input/*.docx to intermediate/*.tex using pandoc."""

import subprocess
import sys
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sanity_check(tex_path):
    with open(tex_path, encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()
    footnotes = re.findall(r"\\footnote\{", text)
    # Extract first 3 footnote previews (up to 80 chars of content)
    previews = re.findall(r"\\footnote\{([^}]{0,80})", text)[:3]

    print(f"\n=== Conversion Summary ===")
    print(f"Lines:      {len(lines):,}")
    print(f"Footnotes:  {len(footnotes)}")
    if previews:
        print("First 3 footnotes:")
        for p in previews:
            print(f"  \\footnote{{{p}...}}" if len(p) == 80 else f"  \\footnote{{{p}}}")
    else:
        print("WARNING: No footnotes found — check if the original .docx had footnotes.")


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/docx_to_tex.py v1")
        sys.exit(1)

    version = sys.argv[1]
    input_path = os.path.join(ROOT, "input", f"input_{version}.docx")
    output_path = os.path.join(ROOT, "intermediate", f"intermediate_{version}.tex")
    media_dir = os.path.join(ROOT, "intermediate", "media")

    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found")
        sys.exit(1)

    os.makedirs(os.path.join(ROOT, "intermediate"), exist_ok=True)

    cmd = [
        "pandoc", input_path,
        "-t", "latex",
        "--standalone",
        "--pdf-engine=xelatex",
        "--wrap=auto",
        "--columns=80",
        f"--extract-media={media_dir}",
        "-o", output_path,
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"Created: {output_path}")

    sanity_check(output_path)


if __name__ == "__main__":
    main()
