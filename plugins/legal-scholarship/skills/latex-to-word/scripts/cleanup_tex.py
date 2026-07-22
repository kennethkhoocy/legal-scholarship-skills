"""Clean up pandoc-generated LaTeX from docx conversion.

Usage: python scripts/cleanup_tex.py <input.tex>
Overwrites the file in place.
"""
import re
import sys

if len(sys.argv) < 2:
    print("Usage: python cleanup_tex.py <input.tex>")
    sys.exit(1)
path = sys.argv[1]

with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Replace \textquotesingle variants with '
text = text.replace("\\textquotesingle{}", "'")
text = text.replace("\\textquotesingle ", "'")
text = text.replace("\\textquotesingle", "'")

# 2. Convert inline footnotes {[}N: ...{]} to \footnote{...}
def convert_footnote(m):
    content = m.group(1).strip()
    # Remove the leading number and colon (e.g., '1: ')
    content = re.sub(r'^\d+:\s*', '', content)
    return '\\footnote{' + content + '}'

text = re.sub(r'\{\[}(.*?)\{]\}', convert_footnote, text, flags=re.DOTALL)

# 3. Simplify subsubsection with texorpdfstring+textbf to subsection
text = re.sub(
    r'\\subsubsection\{\\texorpdfstring\{\\textbf\{(.*?)\}\}\{.*?\}\}',
    lambda m: '\\subsection{' + m.group(1) + '}',
    text,
    flags=re.DOTALL
)

# 4. Remove excessively long labels
text = re.sub(r'\\label\{[^}]{50,}\}', '', text)

# 5. Clean up any remaining {[} {]} that aren't footnotes
text = text.replace('{[}', '[')
text = text.replace('{]}', ']')

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

# Report
footnote_count = len(re.findall(r'\\footnote\{', text))
line_count = text.count('\n')
print(f'=== Cleanup Summary ===')
print(f'File:       {path}')
print(f'Lines:      {line_count}')
print(f'Footnotes:  {footnote_count}')
if footnote_count > 0:
    previews = re.findall(r'\\footnote\{([^}]{0,80})', text)
    print(f'First 3 footnotes:')
    for fn in previews[:3]:
        print(f'  \\footnote{{{fn}...}}')
