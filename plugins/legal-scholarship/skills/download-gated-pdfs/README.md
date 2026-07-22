# download-gated-pdfs

Download the actual PDF binary from bot-gated sites via the Wayback Machine's
raw-content (`id_`) URL form. Many think-tank and publisher sites serve an HTML
bot-challenge page instead of the PDF to non-browser clients, and a browser
`User-Agent` header does not help — the downloaded "PDF" turns out to be HTML.
This skill routes the request through the Internet Archive's untouched-original
endpoint, which returns the archived binary itself. Use it when a direct download
of a `.pdf` URL gives you HTML rather than a real PDF, or when a PDF parser
rejects a freshly downloaded file because it is actually a challenge page.

## When to use

- `curl` or a web fetch of a `.pdf` URL returns HTML instead of a PDF, even with
  a browser `User-Agent`.
- A PDF parser fails on a freshly downloaded file with an error such as
  `invalid pdf header: b'<!DOC'` or an unexpected end-of-file / stream error.
- A scraper can parse the PDF to text but you need the original binary file on
  disk (for example, to keep a reference copy).

## How it triggers in Claude Code

This is an auto-activating knowledge skill. Claude Code loads it when a task
matches the symptoms above — a `.pdf` URL that yields HTML, or a PDF-header error
on a supposedly downloaded file. There is nothing to install; the skill provides
the retrieval recipe and the verification step.

## The technique

1. Request the file through the Wayback Machine's raw-content (`id_`) endpoint,
   which serves the original archived binary without rewriting it:

   ```sh
   curl -sL -A "Mozilla/5.0 ... Chrome/126.0 Safari/537.36" \
     "https://web.archive.org/web/<YYYY>id_/<original-pdf-url>" -o out.pdf
   ```

   `<YYYY>` is any year likely to have a snapshot (for instance, the publication
   year); Wayback redirects to the nearest capture. The `id_` suffix after the
   timestamp is what requests the untouched original rather than a rewritten
   page.

2. Verify the download with a PDF library — a bot-challenge page fails
   immediately:

   ```python
   from pypdf import PdfReader
   r = PdfReader("out.pdf"); print(len(r.pages), "pages")
   ```

   A valid file opens and reports a plausible page count, and the first page's
   text should match the expected title.

3. If Wayback has no capture, fall back to another mirror found via search, or
   to a scraper's parsed text when the binary is not strictly needed.

## Requirements

- **curl** (or an equivalent HTTP client) to fetch the archived binary.
- **pypdf** (or any PDF reader) for the verification step.
- Network access to the Internet Archive (`web.archive.org`).

## Folder contents

- `SKILL.md` — the full note, with a worked example (this README summarizes it).

Knowledge-only skill; no scripts.

## Notes and limitations

- Government and open-data hosts are usually not gated — try a direct download
  first; Wayback is the fallback, not the default.
- Wayback captures can be stale for frequently revised documents; check the
  snapshot date if currency matters.
- For parsing or extraction after the download, use a dedicated PDF skill; for
  parsed text when the binary itself is unnecessary, a web-scraping tool is
  often enough.
