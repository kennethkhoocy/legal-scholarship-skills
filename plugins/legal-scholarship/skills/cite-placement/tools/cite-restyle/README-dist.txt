================================================================
  CITATION RESTYLE TOOL
  Convert footnote citation styles in Word documents
================================================================

Converts all footnote citations in a .docx manuscript from one
citation style to another. Powered by Claude AI.

Supported styles:
  - Bluebook (21st ed.)
  - OSCOLA (4th ed.)
  - Chicago (17th ed., notes-bib)
  - APA (7th ed.)
  - McGill Guide (9th ed.)


REQUIREMENTS
────────────
1. Windows 10 or later
2. An Anthropic API key (get one at https://console.anthropic.com)
3. Internet connection (for the AI to process your footnotes)

No Python, no additional software needed.


HOW TO GET AN API KEY
─────────────────────
1. Go to https://console.anthropic.com
2. Create an account (or sign in)
3. Go to Settings > API Keys
4. Click "Create Key"
5. Copy the key (starts with "sk-ant-...")
6. You will paste this key when the tool asks for it on first run


HOW TO USE
──────────
1. Double-click "Citation Restyle Tool.exe"

2. The tool opens a window with two sections:
   - Files: select your input and output manuscripts
   - Citation Style Conversion: select the From and To styles

3. Click "Browse..." next to "Input .docx" and select your
   Word manuscript

4. The "Output .docx" field auto-fills. Change it if you want
   a different output location or filename

5. Under "Citation Style Conversion":
   - "From" = the style your manuscript currently uses
   - "To" = the style you want to convert to

6. Click "Restyle"

7. On first run only: a dialog asks for your Anthropic API key.
   Paste it and click OK. The key is saved locally on your
   computer for future use.

8. A progress window shows the conversion status. This takes
   1-3 minutes for a typical manuscript (150-200 footnotes).

9. When done, a summary dialog shows how many footnotes were
   converted. Open the output file in Word to review.


WHAT GETS CONVERTED
────────────────────
  Yes:
  - Journal article citations (reformatted to target style)
  - Book citations
  - Working paper citations
  - Cross-references (e.g., "supra note 4" to "(n 3)")
  - Id./ibid conversions
  - Introductory signals (See, See also, Cf., etc.)
  - Internal references (Infra/Supra Part)
  - Author formatting (& vs "and", et al. vs "and others")

  No (preserved unchanged):
  - Case citations (jurisdiction-specific)
  - Legislation and regulations
  - Discursive footnotes (author commentary)
  - Contact/author information footnotes


COST
────
The tool uses the Claude Sonnet API. A typical 200-footnote
manuscript costs approximately $0.10-0.20 per conversion.
Your API key is billed directly by Anthropic.


YOUR ORIGINAL FILE IS SAFE
──────────────────────────
The tool never modifies your input file. It creates a new
output file with the restyled footnotes.


TROUBLESHOOTING
───────────────
Q: The tool won't open / shows a security warning.
A: Windows may block downloaded .exe files. Right-click the
   file > Properties > check "Unblock" > OK. Then try again.

Q: "API error" during processing.
A: Check your internet connection and API key. The tool
   retries automatically up to 3 times per batch.

Q: Some footnotes weren't converted.
A: Case citations, legislation, and discursive footnotes are
   intentionally preserved. A changelog is saved next to
   your output file (restyle_changelog.json).

Q: Wrong API key / want to change it.
A: Delete the file at:
   %APPDATA%\cite-restyle\config.json
   The tool will ask for the key again on next run.


CREDITS
───────
Built with the cite-placement skill for Claude Code.
Powered by Anthropic's Claude AI.
