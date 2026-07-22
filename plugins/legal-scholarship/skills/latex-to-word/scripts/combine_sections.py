#!/usr/bin/env python3
"""Combine multiple LaTeX section files into one document.

Usage:
    python combine_sections.py output.tex input1.tex input2.tex [input3.tex ...]

Extracts the body content (between \\begin{document} and \\end{document}) from
each input file, uses the preamble from the first file, and combines them with
\\clearpage separators.

Options:
    --preamble FILE   Use preamble from this file instead of the first input
    --no-clearpage    Don't insert \\clearpage between sections
"""
import argparse
import re
import sys


def extract_preamble(tex):
    """Extract everything before \\begin{document}."""
    m = re.search(r'\\begin\{document\}', tex)
    if m:
        return tex[:m.start()].rstrip()
    return ""


def extract_body(tex):
    """Extract content between \\begin{document} and \\end{document}."""
    m_start = re.search(r'\\begin\{document\}', tex)
    m_end = re.search(r'\\end\{document\}', tex)
    if m_start and m_end:
        return tex[m_start.end():m_end.start()].strip()
    if m_start:
        return tex[m_start.end():].strip()
    # No document environment — treat entire content as body
    return tex.strip()


def main():
    parser = argparse.ArgumentParser(
        description="Combine multiple LaTeX section files into one document."
    )
    parser.add_argument("output", help="Output .tex file path")
    parser.add_argument("inputs", nargs="+", help="Input .tex files to combine")
    parser.add_argument("--preamble", help="Use preamble from this file instead of first input")
    parser.add_argument("--no-clearpage", action="store_true",
                        help="Don't insert \\clearpage between sections")
    args = parser.parse_args()

    # Read all input files
    sections = []
    for path in args.inputs:
        with open(path, "r", encoding="utf-8") as f:
            sections.append((path, f.read()))

    # Get preamble
    if args.preamble:
        with open(args.preamble, "r", encoding="utf-8") as f:
            preamble = extract_preamble(f.read())
    else:
        preamble = extract_preamble(sections[0][1])

    if not preamble:
        print("Warning: no preamble found — output may not compile standalone", file=sys.stderr)

    # Extract bodies
    separator = "\n\n" if args.no_clearpage else "\n\n\\clearpage\n\n"
    bodies = []
    for path, tex in sections:
        body = extract_body(tex)
        if body:
            bodies.append(body)
            print(f"  {path}: {len(body.splitlines())} lines")
        else:
            print(f"  {path}: WARNING — no body content found", file=sys.stderr)

    # Assemble
    combined = preamble + "\n\n"
    combined += "\\begin{document}\n\n"
    combined += separator.join(bodies)
    combined += "\n\n\\end{document}\n"

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(combined)

    # Summary
    print(f"\n=== Combined Document Summary ===")
    print(f"Sections:          {len(bodies)}")
    print(f"Total lines:       {len(combined.splitlines()):,}")
    print(f"\\section count:    {combined.count(chr(92) + 'section{')}")
    print(f"\\subsection count: {combined.count(chr(92) + 'subsection{')}")
    print(f"\\footnote count:   {len(re.findall(r'\\\\footnote\\{', combined))}")
    print(f"Output:            {args.output}")


if __name__ == "__main__":
    main()
