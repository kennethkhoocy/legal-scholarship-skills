#!/usr/bin/env python3
"""Convert square-bracket citations {[}N: text{]} to \\footnote{text} in LaTeX files.

Some manuscripts use inline square-bracket citations [N: citation text] instead
of Word's built-in footnote feature. After pandoc conversion to LaTeX, these
appear as escaped brackets: {[}N: text{]} or {[}N{]} (bare number, no content).

This script converts them to proper \\footnote{} commands:
  {[}N: citation text{]}  ->  \\footnote{citation text}
  {[}N{]}                 ->  \\footnote{}

Handles:
  - Multi-line bracket content (pandoc wraps at 80 chars)
  - Nested brackets {[}N: {[}editorial note{]}{]}
  - URLs and special LaTeX characters inside brackets
  - Preceding space removal (footnote sits flush against text)

Usage:
    python convert_bracket_footnotes.py input.tex output.tex
"""
import re
import sys


def convert_bracket_footnotes(tex_content):
    """Convert {[}N: text{]} and {[}N{]} patterns to \\footnote{text}.

    Returns (converted_content, footnote_count, bare_count) where bare_count
    is the number of bare-number footnotes {[}N{]} that had no content.
    """
    result = []
    i = 0
    footnote_count = 0
    bare_count = 0
    n = len(tex_content)

    while i < n:
        # Look for {[} followed by a digit
        if (tex_content[i:i + 3] == '{[}'
                and i + 3 < n
                and tex_content[i + 3].isdigit()):
            # Match the number
            m = re.match(r'\d+', tex_content[i + 3:])
            num = m.group(0)
            after_num = i + 3 + len(num)

            # Case 1: {[}N{]} -- bare number, no content
            if tex_content[after_num:after_num + 3] == '{]}':
                # Strip preceding space
                if result and result[-1] == ' ':
                    result.pop()
                result.append('\\footnote{}')
                i = after_num + 3
                footnote_count += 1
                bare_count += 1
                continue

            # Case 2: {[}N: content{]} -- with content after colon
            if tex_content[after_num] == ':':
                content_start = after_num + 1
                # Skip whitespace (space, tab, newline) after colon
                while (content_start < n
                       and tex_content[content_start] in ' \t\n\r'):
                    content_start += 1

                # Find the matching {]} considering nested {[}...{]}
                depth = 1
                j = content_start
                while j < n and depth > 0:
                    if tex_content[j:j + 3] == '{[}':
                        depth += 1
                        j += 3
                    elif tex_content[j:j + 3] == '{]}':
                        depth -= 1
                        if depth == 0:
                            break
                        j += 3
                    else:
                        j += 1

                if depth == 0:
                    content = tex_content[content_start:j].strip()
                    # Strip preceding space
                    if result and result[-1] == ' ':
                        result.pop()
                    result.append('\\footnote{')
                    result.append(content)
                    result.append('}')
                    i = j + 3  # skip past closing {]}
                    footnote_count += 1
                    continue

        # Default: copy character as-is
        result.append(tex_content[i])
        i += 1

    return ''.join(result), footnote_count, bare_count


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} input.tex output.tex")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    converted, total, bare = convert_bracket_footnotes(content)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(converted)

    print(f"=== Bracket Footnote Conversion ===")
    print(f"Total converted:     {total}")
    print(f"  With content:      {total - bare}")
    print(f"  Bare number only:  {bare}")
    print(f"Output written to:   {output_path}")

    if bare > 0:
        print(f"\nNote: {bare} footnote(s) had no content (bare [N] references).")
        print("These were converted to empty \\footnote{} commands.")
        print("Review the output and add footnote text where needed.")


if __name__ == '__main__':
    main()
