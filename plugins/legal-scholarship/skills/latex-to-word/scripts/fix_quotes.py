#!/usr/bin/env python3
r"""Replace \textquotesingle with proper LaTeX quotation marks.

Usage:
    python fix_quotes.py <input.tex>

Overwrites the file in place.

Handles:
- Quoted terms: \textquotesingle TERM\textquotesingle{} -> ``TERM''
- Possessive: \textquotesingle s -> 's
- Plural possessive / trailing: WORD\textquotesingle{} -> WORD'
- Standalone: remaining \textquotesingle -> '
"""
import re
import sys


def fix_quotes(content):
    r"""Replace \textquotesingle patterns with proper LaTeX quotes.

    Strategy:
    1. Detect paired quotes (opening + closing) and convert to ``...''
    2. Convert possessives (\textquotesingle s) to 's
    3. Convert trailing (\textquotesingle{}) to closing '
    4. Convert any remaining standalone to '
    """
    original_count = content.count(r'\textquotesingle')

    # Step 1: Paired quotes — \textquotesingle CONTENT\textquotesingle{}
    # Opening quote is typically preceded by space/newline/start and followed by a letter.
    # Closing quote is \textquotesingle{} or \textquotesingle before punctuation.
    # Use a regex to find pairs: opening \textquotesingle followed by content,
    # then closing \textquotesingle{} (with {} or before punctuation/space).
    def replace_pair(m):
        return "``" + m.group(1) + "''"

    # Match pairs: \textquotesingle followed by content, then \textquotesingle{}
    # Content can span multiple lines (pandoc wraps at 80 chars)
    content = re.sub(
        r"\\textquotesingle\s(.*?)\\textquotesingle\{\}",
        replace_pair,
        content,
        flags=re.DOTALL
    )

    # Also handle closing without {} (before colon, period, comma)
    content = re.sub(
        r"\\textquotesingle\s(.*?)\\textquotesingle([,:.\s])",
        lambda m: "``" + m.group(1) + "''" + m.group(2),
        content,
        flags=re.DOTALL
    )

    # Step 2: Possessive — \textquotesingle s (with space or before punctuation)
    content = re.sub(r"\\textquotesingle\ss(?=[\s,.\)\]])", "'s", content)
    content = content.replace(r"\textquotesingle s ", "'s ")
    content = content.replace(r"\textquotesingle s,", "'s,")
    content = content.replace(r"\textquotesingle s.", "'s.")

    # Step 3: Trailing — \textquotesingle{}
    content = content.replace(r"\textquotesingle{}", "'")

    # Step 4: Any remaining standalone
    content = content.replace(r"\textquotesingle", "'")

    final_count = content.count(r'\textquotesingle')
    return content, original_count, final_count


def main():
    if len(sys.argv) < 2:
        print("Usage: python fix_quotes.py <input.tex>")
        sys.exit(1)

    path = sys.argv[1]

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    content, original, remaining = fix_quotes(content)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Replaced {original - remaining} of {original} \\textquotesingle instances.")
    if remaining > 0:
        print(f"WARNING: {remaining} remaining — review manually.")
        for m in re.finditer(r'\\textquotesingle', content):
            ctx = content[max(0, m.start() - 30):m.start() + 50]
            print(f"  ...{ctx}...")


if __name__ == "__main__":
    main()
