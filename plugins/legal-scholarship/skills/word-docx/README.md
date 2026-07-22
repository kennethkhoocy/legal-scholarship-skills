# word-docx

A unified command-line skill for Microsoft Word `.docx` review and generation.
It converts `.docx` content into structured JSON/Markdown before any LLM
reasoning, and it builds new `.docx` files from structured specs, so the model
never parses raw OOXML and never edits a source file in place.

## Core principle

Work proceeds in two stages, and source documents are treated as read-only
throughout:

1. **Extract** structured data (JSON/Markdown) from the `.docx`.
2. **Reason** over that structured data, then **build** a new `.docx` if a
   document is needed.

The LLM is never asked to read raw `.docx` XML, and the original file is never
changed in place.

## Install

Copy the `word-docx` folder to `~/.claude/skills/word-docx/` for Claude Code or
`~/.agents/skills/word-docx/` for Codex, then install its Python dependencies:

```bash
pip install -r requirements.txt
```

The Python-native commands — `inspect`, `extract-comments`, `extract-revisions`,
`extract-text`, `apply-edits`, `apply-tracked-edits`, `apply-non-tracked-edits`,
`render-pdf`, `audit-ooxml`, and the python-routed half of `build` — run with no
further setup.

Restart the host or start a new session so it discovers the skill. It
auto-activates for Word-document tasks; explicit invocation is `/word-docx` in
Claude Code or `$word-docx` in Codex.

### Optional backends

Several commands shell out to Anthropic's `document-skills` plugin: `validate`,
`accept-changes`, `convert-doc`, `unpack`, `pack`, `simplify-redlines`,
`docx-to-images`, and the comment-authoring half of `add-comment`. Install once:

```bash
claude plugin marketplace add anthropics/skills
claude plugin install document-skills@anthropic-agent-skills
```

The JS-routed `build` path — table of contents, multi-column layout,
headers/footers with page numbers, internal hyperlinks, and native footnotes —
needs Node ≥ 18 and the `docx` npm package:

```bash
npm install -g docx
```

When a command needs a backend that is not installed, it raises a clear error
naming the exact install command rather than failing silently.

## Commands

Everything runs through one entry point:

```bash
python scripts/word_docx.py <command> [options]
```

| User intent | Command | Primary library |
|-------------|---------|-----------------|
| Read comments / reviewer feedback | `extract-comments` | docx2python |
| Read tracked changes / redlines | `extract-revisions` | docx-revisions, OOXML fallback |
| Read ordinary text and tables | `extract-text` | python-docx |
| Full inspection (all of the above) | `inspect` | all |
| Build a new Word document | `build` | python-docx or docxtpl / Node `docx` |
| Render to PDF | `render-pdf` | LibreOffice |
| Apply edits (auto-detect tracked vs silent) | `apply-edits` | lxml + zipfile |
| Apply tracked edits (force) | `apply-tracked-edits` | lxml + zipfile |
| Apply silent edits (force) | `apply-non-tracked-edits` | lxml + zipfile |
| Add, reply to, or resolve a comment | `add-comment` | hybrid (unpack → edit → pack) |
| Structural OOXML lint | `audit-ooxml` | lxml |

`apply-edits` is the recommended default for edits: it detects whether the input
already contains tracked changes and matches that mode, applying `w:ins`/`w:del`
markup only when the document is itself tracked.

## Typical workflow

```text
1. inspect marked_up.docx --out ./review
2. LLM reads review/comments.json and review/revisions.json
3. LLM writes response_spec.json
4. build --spec response_spec.json --out response_to_comments.docx
```

The `build` spec is a single JSON object describing the document. A spec that
stays within the Python features (title, sections, paragraphs, page margins,
footnotes via `[^N]` markers) routes to python-docx automatically; a spec that
uses a JS-only feature (`toc`, `columns`, `page_sections`, `native_footnotes`)
routes to the Node `docx` backend. Set `runtime` explicitly to override the
auto-routing. The full spec shape and per-command options are documented in
[`SKILL.md`](SKILL.md), with runnable examples under [`examples/`](examples/).

## Output conventions

- Every command writes to an explicit `--out` directory, never alongside the
  source file.
- JSON is UTF-8 with `ensure_ascii=False`.
- Comment IDs are `C001`, `C002`, …; revision IDs are `R001`, `R002`, ….
- Diagnostics are recorded as warnings in a manifest rather than raised as
  crashes, so a malformed element degrades one result instead of the whole run.

## Failure modes

| Error | Fix |
|-------|-----|
| `AnthropicSkillNotInstalledError` | Run the two `claude plugin` commands above. |
| `BuildSpecRequiresJSError` | Remove the JS-only spec field, or set `"runtime": "auto"`. |
| `NodeNotInstalledError` | Install Node ≥ 18 from nodejs.org. |
| `DocxPackageMissingError` | Run `npm install -g docx`. |
