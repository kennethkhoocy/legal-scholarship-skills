# Workflow C — Assembling .tex from Mixed Sources (Knowledge Patterns)

This is **workflow C** of the `latex-to-word` skill. It is knowledge-only — there are no scripts to run; the patterns below are applied when authoring a pipeline that assembles a single `.tex` from PDF/docx/LLM-generated content.

# Generating LaTeX from Mixed-Source Content

## Problem

When building a pipeline that combines text from multiple sources into a single
.tex document, each source produces text in a different format. Applying a single
escape/conversion strategy to all sources causes cascading breakage:

- PDF-extracted text has dollar signs as currency (`$200,000`) that must be escaped
- .docx-extracted text has Unicode characters (Greek letters, em-dashes) that need
  `\DeclareUnicodeCharacter` mappings
- LLM-generated text contains raw LaTeX commands (`\textbf{}`, `$\frac{D}{E}$`,
  `\begin{enumerate}`) that must NOT be escaped

## Context / Trigger Conditions

- Building a pipeline that parses PDFs/docx and generates .tex output
- Using an LLM (Claude, GPT) to elaborate or generate answer text that goes into LaTeX
- Seeing errors like `\textbackslash{}textbf` (escaped LaTeX commands), broken math mode,
  or `\{}` artifacts in compiled PDFs
- `pdflatex` fails with "Extra }", "Undefined control sequence", or
  "File ended while scanning use of \textbf"

## Solution

### The Two-Track Architecture

The key insight: **don't run LLM-generated LaTeX through your escape pipeline.**

```python
if source_is_llm_generated:
    # LLM was prompted to output valid LaTeX directly.
    # Pass through as-is — no escaping, no markdown conversion.
    formatted_text = raw_llm_text
else:
    # Text from PDF/docx extraction — needs full escaping.
    formatted_text = escape_latex(raw_extracted_text)
```

### Prompting LLMs to output LaTeX directly

Instead of having the LLM write markdown (which you then convert), instruct it
to write valid LaTeX:

```
OUTPUT VALID LaTeX directly. The text will be placed inside a .tex document.
Use $...$ for inline math and \[ ... \] for display math.
Use \$ for literal dollar signs (currency amounts like \$200,000).
Use \textbf{} for bold, \textit{} for italic.
Use \begin{enumerate}[label=(\alph*)] for sub-parts.
Do NOT use markdown formatting (**bold**, *italic*, - bullets, | tables |).
```

### Strip code fences from LLM output

LLMs often wrap LaTeX in markdown code fences even when told not to:

```python
# Strip ```latex ... ``` fences
output = re.sub(r'^```(?:latex|tex)?\s*\n', '', output)
output = re.sub(r'\n```\s*$', '', output)
```

### Escaping pipeline for extracted text

For text from PDFs/docx that is NOT already LaTeX:

1. **Protect math first**: Extract `$...\command...$` blocks into placeholders
2. **Protect block placeholders**: `%%BLOCK_N%%` for tables/images
3. **Protect markdown formatting**: Convert `**bold**`, `*italic*` to `%%BOLD:...%%` etc.
4. **Escape special chars**: `& % $ # _ { } ~ ^ \`
5. **Restore in reverse order**: markdown format → blocks → math

The restore order matters because inner placeholders (math inside list items)
must be exposed before outer ones are restored.

### Unicode in LaTeX template

Add `\DeclareUnicodeCharacter` for common symbols from PDF/docx extraction:

```latex
\DeclareUnicodeCharacter{03B2}{\ensuremath{\beta}}
\DeclareUnicodeCharacter{0394}{\ensuremath{\Delta}}
\DeclareUnicodeCharacter{2248}{\ensuremath{\approx}}
\DeclareUnicodeCharacter{2713}{\checkmark}
```

### Filenames with dots and spaces

`pdflatex` on Windows fails with output paths containing dots followed by spaces
(e.g., `10. Understanding Options.tex`). Fix with `-job-name`:

```python
job_name = os.path.splitext(os.path.basename(tex_path))[0]
cmd = ["pdflatex", "-interaction=batchmode",
       f"-output-directory={output_dir}",
       f"-job-name={job_name}", tex_path]
```

## Verification

- No `\textbackslash{}`, `\{\}`, or `XMATHX` placeholders in compiled PDF
- Math renders correctly (not escaped as `\$...\$`)
- Bold/italic renders (not raw `**text**`)
- Currency amounts show as `$200,000` (not in math mode)

## Notes

- Always use `-interaction=batchmode` for pdflatex to prevent hanging on errors
- Use `string.Template` (not f-strings) for LaTeX template substitution — f-strings
  conflict with LaTeX backslashes
- When using `subprocess` to call `claude -p` on Windows, set `encoding="utf-8"` and
  `PYTHONIOENCODING=utf-8` in the env to handle Greek letters
- Cache successful LLM elaborations to avoid re-processing on retries
