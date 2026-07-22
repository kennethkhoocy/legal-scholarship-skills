"""word-docx CLI — unified entry point for .docx review and generation workflows."""

import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

import json
from datetime import datetime, timezone

import typer
from rich import print as rprint
from rich.console import Console

from models import BuildSpec, DiagnosticEntry, EditOperation, Manifest

app = typer.Typer(
    name="word-docx",
    help="Microsoft Word .docx review and generation workflows.",
    no_args_is_help=True,
)
console = Console()


def _write_json(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


@app.command()
def inspect(
    input: Path = typer.Argument(..., help="Path to .docx file"),
    out: Path = typer.Option(..., help="Output directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run full inspection: comments, revisions, text, and OOXML audit."""
    from audit_ooxml import audit_ooxml, validate_docx, write_audit
    from extract_comments import extract_comments, write_comments
    from extract_revisions import extract_revisions, write_revisions
    from extract_text import extract_text, write_text

    all_diagnostics: list[DiagnosticEntry] = []
    written_files: list[str] = []

    # Validate
    validation = validate_docx(input)
    all_diagnostics.extend(validation)
    errors = [d for d in validation if d.level == "error"]
    if errors:
        for e in errors:
            rprint(f"[red]ERROR:[/red] {e.message}")
        raise typer.Exit(1)

    out.mkdir(parents=True, exist_ok=True)

    if verbose:
        rprint(f"[blue]Inspecting:[/blue] {input}")

    # Comments
    if verbose:
        rprint("[blue]Extracting comments...[/blue]")
    comments, diags = extract_comments(input)
    all_diagnostics.extend(diags)
    write_comments(comments, out)
    written_files.extend(["comments.json", "comments.md"])

    # Revisions
    if verbose:
        rprint("[blue]Extracting revisions...[/blue]")
    revisions, diags = extract_revisions(input)
    all_diagnostics.extend(diags)
    write_revisions(revisions, out)
    written_files.extend(["revisions.json", "revisions.md"])

    # Text
    if verbose:
        rprint("[blue]Extracting text...[/blue]")
    paragraphs, markdown, diags = extract_text(input)
    all_diagnostics.extend(diags)
    write_text(paragraphs, markdown, out)
    written_files.extend(["document.md", "paragraphs.json"])

    # OOXML audit
    if verbose:
        rprint("[blue]Running OOXML audit...[/blue]")
    audit_result = audit_ooxml(input)
    write_audit(audit_result, all_diagnostics, out)
    written_files.append("diagnostics.json")

    # Manifest
    written_files.append("manifest.json")
    manifest = Manifest(
        input_file=str(input.resolve()),
        output_dir=str(out.resolve()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        files=written_files,
        diagnostics=all_diagnostics,
    )
    _write_json(manifest.model_dump(), out / "manifest.json")

    # Summary
    errors = [d for d in all_diagnostics if d.level == "error"]
    warnings = [d for d in all_diagnostics if d.level == "warning"]
    rprint(f"[green]Inspection complete.[/green] {len(written_files)} files written to {out}")
    rprint(f"  Comments: {len(comments)}  Revisions: {len(revisions)}  Paragraphs: {len(paragraphs)}")
    if errors:
        rprint(f"  [red]Errors: {len(errors)}[/red]")
        for e in errors:
            rprint(f"    - {e.message}")
    if warnings:
        rprint(f"  [yellow]Warnings: {len(warnings)}[/yellow]")
        for w in warnings:
            rprint(f"    - {w.message}")
    if errors:
        raise typer.Exit(1)


@app.command("extract-comments")
def extract_comments_cmd(
    input: Path = typer.Argument(..., help="Path to .docx file"),
    out: Path = typer.Option(..., help="Output directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Extract comments from a .docx file."""
    from audit_ooxml import validate_docx
    from extract_comments import extract_comments, write_comments

    _validate_or_exit(input)
    out.mkdir(parents=True, exist_ok=True)

    comments, diagnostics = extract_comments(input)
    write_comments(comments, out)

    if diagnostics:
        _write_json([d.model_dump() for d in diagnostics], out / "diagnostics.json")

    rprint(f"[green]Extracted {len(comments)} comments.[/green]")
    if verbose:
        for c in comments:
            rprint(f"  {c.comment_id}: {c.author} — {c.comment_text[:60]}...")
    _check_diagnostics_or_exit(diagnostics)


@app.command("extract-revisions")
def extract_revisions_cmd(
    input: Path = typer.Argument(..., help="Path to .docx file"),
    out: Path = typer.Option(..., help="Output directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Extract tracked changes from a .docx file."""
    from extract_revisions import extract_revisions, write_revisions

    _validate_or_exit(input)
    out.mkdir(parents=True, exist_ok=True)

    revisions, diagnostics = extract_revisions(input)
    write_revisions(revisions, out)

    if diagnostics:
        _write_json([d.model_dump() for d in diagnostics], out / "diagnostics.json")

    rprint(f"[green]Extracted {len(revisions)} revisions.[/green]")
    if verbose:
        for r in revisions:
            rprint(f"  {r.revision_id} [{r.type}]: {r.text[:60]}...")
    _check_diagnostics_or_exit(diagnostics)


@app.command("extract-text")
def extract_text_cmd(
    input: Path = typer.Argument(..., help="Path to .docx file"),
    out: Path = typer.Option(..., help="Output directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Extract ordinary text and tables as Markdown and JSON."""
    from extract_text import extract_text, write_text

    _validate_or_exit(input)
    out.mkdir(parents=True, exist_ok=True)

    paragraphs, markdown, diagnostics = extract_text(input)
    write_text(paragraphs, markdown, out)

    if diagnostics:
        _write_json([d.model_dump() for d in diagnostics], out / "diagnostics.json")

    rprint(f"[green]Extracted {len(paragraphs)} paragraphs.[/green]")
    _check_diagnostics_or_exit(diagnostics)


@app.command()
def build(
    spec: Path = typer.Option(..., help="Path to JSON build spec"),
    out: Path = typer.Option(..., help="Output .docx path"),
    template: Path | None = typer.Option(None, help="Optional .docx template for docxtpl"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Build a new .docx from a structured JSON spec."""
    from build_docx import build_from_spec, write_build_manifest

    if not spec.exists():
        rprint(f"[red]Spec file not found:[/red] {spec}")
        raise typer.Exit(1)

    try:
        with open(spec, encoding="utf-8") as f:
            data = json.load(f)
        build_spec = BuildSpec(**data)
    except json.JSONDecodeError as e:
        rprint(f"[red]Invalid JSON in spec file:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        rprint(f"[red]Invalid spec:[/red] {e}")
        raise typer.Exit(1)

    if verbose:
        rprint(f"[blue]Building:[/blue] {build_spec.title}")
        rprint(f"  Sections: {len(build_spec.sections)}  Items: {len(build_spec.items)}")

    from build_docx import BuildSpecRequiresJSError

    try:
        diagnostics = build_from_spec(build_spec, out, template)
    except BuildSpecRequiresJSError as e:
        rprint(f"[red]ERROR:[/red] BuildSpecRequiresJSError: {e}")
        raise typer.Exit(1)
    except Exception as e:
        # Surface NodeNotInstalledError / DocxPackageMissingError with a clean message
        name = type(e).__name__
        if name in ("NodeNotInstalledError", "DocxPackageMissingError"):
            rprint(f"[red]ERROR ({name}):[/red] {e}")
            raise typer.Exit(2)
        raise  # unknown — let the traceback through for debugging
    write_build_manifest(out, build_spec, diagnostics, template)

    errors = [d for d in diagnostics if d.level == "error"]
    if errors:
        for e in errors:
            rprint(f"[red]ERROR:[/red] {e.message}")
        raise typer.Exit(1)

    rprint(f"[green]Built:[/green] {out}")
    if verbose:
        rprint(f"  Manifest: {out.with_suffix('.manifest.json')}")
        for d in diagnostics:
            rprint(f"  [{d.level.upper()}] {d.source}: {d.message}")


@app.command("audit-ooxml")
def audit_ooxml_cmd(
    input: Path = typer.Argument(..., help="Path to .docx file"),
    out: Path = typer.Option(..., help="Output directory for the audit report"),
) -> None:
    """Run a fast OOXML lint on a .docx file (warnings only).

    For schema-grade validation that detects element-level defects, use the
    `validate` command instead. This command produces a diagnostics.json
    file in `--out` summarising part counts and any structural warnings.
    """
    from audit_ooxml import audit_ooxml, write_audit

    _validate_or_exit(input)
    out.mkdir(parents=True, exist_ok=True)
    audit_result = audit_ooxml(input)
    write_audit(audit_result, [], out)
    rprint(f"[green]Audit complete:[/green] {out / 'diagnostics.json'}")


@app.command("render-pdf")
def render_pdf_cmd(
    input: Path = typer.Argument(..., help="Path to .docx file"),
    out: Path = typer.Option(..., help="Output .pdf path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Render a .docx to PDF using LibreOffice."""
    from render_pdf import render_pdf

    _validate_or_exit(input)

    diagnostics = render_pdf(input, out, verbose=verbose)
    errors = [d for d in diagnostics if d.level == "error"]
    if errors:
        for e in errors:
            rprint(f"[red]ERROR:[/red] {e.message}")
        raise typer.Exit(1)

    rprint(f"[green]Rendered:[/green] {out}")


@app.command("validate")
def validate_cmd(
    input: Path = typer.Argument(..., help="Path to .docx file"),
) -> None:
    """Validate a .docx with Anthropic's schema-grade validator (auto-repairs common defects)."""
    from commands.validate import run

    code = run(input)
    raise typer.Exit(code)


@app.command("accept-changes")
def accept_changes_cmd(
    input: Path = typer.Argument(..., help="Path to source .docx file"),
    out: Path = typer.Option(..., help="Output .docx path"),
) -> None:
    """Accept all tracked changes; produce a clean output document (requires LibreOffice)."""
    from commands.accept_changes import run

    _reject_in_place_overwrite(input, out)
    code = run(input, out)
    raise typer.Exit(code)


@app.command("unpack")
def unpack_cmd(
    input: Path = typer.Argument(..., help="Path to .docx file"),
    out: Path = typer.Option(..., help="Output directory for the unpacked XML"),
    no_merge_runs: bool = typer.Option(False, "--no-merge-runs", help="Skip adjacent-run merging"),
) -> None:
    """Unpack a .docx for direct XML editing (Anthropic office/unpack.py)."""
    from commands.unpack import run

    code = run(input, out, merge_runs=not no_merge_runs)
    raise typer.Exit(code)


@app.command("pack")
def pack_cmd(
    unpacked_dir: Path = typer.Argument(..., help="Unpacked directory produced by `unpack`"),
    out: Path = typer.Option(..., help="Output .docx path"),
    original: Path | None = typer.Option(None, help="Optional original .docx for relationship preservation"),
    no_validate: bool = typer.Option(False, "--no-validate", help="Skip post-pack validation"),
) -> None:
    """Repack an unpacked directory back into a .docx (Anthropic office/pack.py)."""
    from commands.pack import run

    code = run(unpacked_dir, out, original=original, validate=not no_validate)
    raise typer.Exit(code)


@app.command("add-comment")
def add_comment_cmd(
    input: Path = typer.Argument(..., help="Path to source .docx file"),
    out: Path = typer.Option(..., help="Output .docx path"),
    reply_to: str | None = typer.Option(None, "--reply-to", help="Reply to comment ID (e.g. C001)"),
    anchor_paragraph: int | None = typer.Option(None, help="Zero-based paragraph index for a new comment"),
    anchor_text: str | None = typer.Option(None, help="Text span to anchor a new comment"),
    resolve: str | None = typer.Option(None, "--resolve", help="Mark comment ID as done"),
    text: str | None = typer.Option(None, help="Comment body (required for reply and new modes)"),
    author: str = typer.Option("Claude", help="Comment author"),
) -> None:
    """Add a comment to a .docx: reply to existing, anchor a new one, or resolve."""
    from add_comment import add_comment
    from models import AddCommentSpec

    if resolve is not None:
        mode = "resolve"
    elif reply_to is not None:
        mode = "reply"
    elif anchor_paragraph is not None and anchor_text is not None:
        mode = "new"
    else:
        rprint("[red]ERROR:[/red] Specify one of --reply-to, --resolve, or --anchor-paragraph + --anchor-text.")
        raise typer.Exit(1)

    _reject_in_place_overwrite(input, out)
    spec = AddCommentSpec(
        mode=mode,
        text=text,
        author=author,
        reply_to=reply_to,
        anchor_paragraph=anchor_paragraph,
        anchor_text=anchor_text,
        resolve=resolve,
    )
    code = add_comment(input, out, spec)
    raise typer.Exit(code)


@app.command("simplify-redlines")
def simplify_redlines_cmd(
    input: Path = typer.Argument(..., help="Path to .docx file with tracked changes"),
    out: Path = typer.Option(..., help="Output .docx path"),
) -> None:
    """Collapse noisy redline markup (Anthropic office/helpers/simplify_redlines.py)."""
    from commands.simplify_redlines import run

    _reject_in_place_overwrite(input, out)
    code = run(input, out)
    raise typer.Exit(code)


@app.command("docx-to-images")
def docx_to_images_cmd(
    input: Path = typer.Argument(..., help="Path to .docx file"),
    out_dir: Path = typer.Option(..., "--out-dir", help="Output directory for page-*.jpg files"),
    dpi: int = typer.Option(150, help="Output resolution"),
) -> None:
    """Render a .docx as one JPEG per page (via LibreOffice PDF + pdftoppm)."""
    from commands.docx_to_images import run

    code = run(input, out_dir, dpi=dpi)
    raise typer.Exit(code)


@app.command("convert-doc")
def convert_doc_cmd(
    input: Path = typer.Argument(..., help="Path to legacy .doc file"),
    out_dir: Path = typer.Option(..., "--out-dir", help="Output directory for the .docx"),
) -> None:
    """Convert a legacy .doc file to .docx (requires LibreOffice via Anthropic's wrapper)."""
    from commands.convert_doc import run

    code = run(input, out_dir)
    raise typer.Exit(code)


@app.command("apply-tracked-edits")
def apply_tracked_edits_cmd(
    input: Path = typer.Argument(..., help="Path to source .docx file"),
    edits: Path = typer.Option(..., help="Path to edits JSON file"),
    out: Path = typer.Option(..., help="Output .docx path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Apply tracked edits to a .docx file via direct OOXML manipulation.

    Supports replace, insert, and delete operations scoped to individual
    paragraphs, with author and date metadata on each tracked change.
    """
    _reject_in_place_overwrite(input, out)
    _validate_or_exit(input)

    if not edits.exists():
        rprint(f"[red]Edits file not found:[/red] {edits}")
        raise typer.Exit(1)

    try:
        with open(edits, encoding="utf-8") as f:
            raw = json.load(f)
        operations = [EditOperation(**op) for op in raw]
    except json.JSONDecodeError as e:
        rprint(f"[red]Invalid JSON in edits file:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        rprint(f"[red]Invalid edits spec:[/red] {e}")
        raise typer.Exit(1)

    if verbose:
        rprint(f"[blue]Edits to apply:[/blue] {len(operations)}")
        for op in operations:
            rprint(f"  {op.operation} at paragraph {op.paragraph_index}")

    from apply_edits import apply_edits

    diagnostics = apply_edits(input, operations, out)

    errors = [d for d in diagnostics if d.level == "error"]
    warnings = [d for d in diagnostics if d.level == "warning"]
    infos = [d for d in diagnostics if d.level == "info"]

    if warnings and verbose:
        for w in warnings:
            rprint(f"[yellow]WARNING:[/yellow] {w.message}")

    if errors:
        for e in errors:
            rprint(f"[red]ERROR:[/red] {e.message}")
        raise typer.Exit(1)

    for info in infos:
        rprint(f"[green]{info.message}[/green]")


@app.command("apply-non-tracked-edits")
def apply_non_tracked_edits_cmd(
    input: Path = typer.Argument(..., help="Path to source .docx file"),
    edits: Path = typer.Option(..., help="Path to edits JSON file"),
    out: Path = typer.Option(..., help="Output .docx path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Apply silent edits to a .docx file (no tracked changes markup).

    Same JSON format as apply-tracked-edits, but edits are applied directly
    without w:ins / w:del wrappers — the output reads as if the text was
    always written that way.
    """
    _reject_in_place_overwrite(input, out)
    _validate_or_exit(input)

    if not edits.exists():
        rprint(f"[red]Edits file not found:[/red] {edits}")
        raise typer.Exit(1)

    try:
        with open(edits, encoding="utf-8") as f:
            raw = json.load(f)
        operations = [EditOperation(**op) for op in raw]
    except json.JSONDecodeError as e:
        rprint(f"[red]Invalid JSON in edits file:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        rprint(f"[red]Invalid edits spec:[/red] {e}")
        raise typer.Exit(1)

    if verbose:
        rprint(f"[blue]Silent edits to apply:[/blue] {len(operations)}")
        for op in operations:
            rprint(f"  {op.operation} at paragraph {op.paragraph_index}")

    from apply_edits import apply_edits_silent

    diagnostics = apply_edits_silent(input, operations, out)

    errors = [d for d in diagnostics if d.level == "error"]
    warnings = [d for d in diagnostics if d.level == "warning"]
    infos = [d for d in diagnostics if d.level == "info"]

    if warnings and verbose:
        for w in warnings:
            rprint(f"[yellow]WARNING:[/yellow] {w.message}")

    if errors:
        for e in errors:
            rprint(f"[red]ERROR:[/red] {e.message}")
        raise typer.Exit(1)

    for info in infos:
        rprint(f"[green]{info.message}[/green]")


def _has_tracked_changes(input_path: Path) -> bool:
    """Check if a .docx contains existing tracked changes."""
    import zipfile
    from lxml import etree
    try:
        with zipfile.ZipFile(input_path, "r") as zf:
            if "word/document.xml" not in zf.namelist():
                return False
            doc_xml = zf.read("word/document.xml")
        tree = etree.fromstring(doc_xml)
        w_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        for tag in ("ins", "del", "moveFrom", "moveTo", "rPrChange", "pPrChange"):
            if list(tree.iter(f"{{{w_ns}}}{tag}")):
                return True
    except Exception:
        pass
    return False


@app.command("apply-edits")
def apply_edits_auto_cmd(
    input: Path = typer.Argument(..., help="Path to source .docx file"),
    edits: Path = typer.Option(..., help="Path to edits JSON file"),
    out: Path = typer.Option(..., help="Output .docx path"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Apply edits with auto-detection: tracked if input has tracked changes, silent otherwise."""
    _reject_in_place_overwrite(input, out)
    _validate_or_exit(input)

    if not edits.exists():
        rprint(f"[red]Edits file not found:[/red] {edits}")
        raise typer.Exit(1)

    try:
        with open(edits, encoding="utf-8") as f:
            raw = json.load(f)
        operations = [EditOperation(**op) for op in raw]
    except json.JSONDecodeError as e:
        rprint(f"[red]Invalid JSON in edits file:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        rprint(f"[red]Invalid edits spec:[/red] {e}")
        raise typer.Exit(1)

    tracked = _has_tracked_changes(input)
    mode = "tracked" if tracked else "silent"

    if verbose:
        rprint(f"[blue]Auto-detected mode:[/blue] {mode} ({len(operations)} edits)")
        for op in operations:
            rprint(f"  {op.operation} at paragraph {op.paragraph_index}")

    from apply_edits import apply_edits as apply_tracked, apply_edits_silent

    if tracked:
        rprint("[blue]Input has tracked changes — applying as tracked edits.[/blue]")
        diagnostics = apply_tracked(input, operations, out)
    else:
        rprint("[blue]No tracked changes detected — applying as silent edits.[/blue]")
        diagnostics = apply_edits_silent(input, operations, out)

    errors = [d for d in diagnostics if d.level == "error"]
    warnings = [d for d in diagnostics if d.level == "warning"]
    infos = [d for d in diagnostics if d.level == "info"]

    if warnings and verbose:
        for w in warnings:
            rprint(f"[yellow]WARNING:[/yellow] {w.message}")

    if errors:
        for e in errors:
            rprint(f"[red]ERROR:[/red] {e.message}")
        raise typer.Exit(1)

    for info in infos:
        rprint(f"[green]{info.message}[/green]")


def _validate_or_exit(input_path: Path) -> None:
    """Validate input file or exit."""
    from audit_ooxml import validate_docx

    diagnostics = validate_docx(input_path)
    errors = [d for d in diagnostics if d.level == "error"]
    if errors:
        for e in errors:
            rprint(f"[red]ERROR:[/red] {e.message}")
        raise typer.Exit(1)


def _reject_in_place_overwrite(input_path: Path, out_path: Path) -> None:
    """Refuse to write the output on top of the source file.

    SKILL.md mandates that source .docx files are never modified in place
    (codex audit issue 4). Mutating commands route through this helper at
    the top of their CLI body; pack/convert-doc are excluded because their
    inputs and outputs cannot collide.
    """
    try:
        same = input_path.resolve(strict=False) == out_path.resolve(strict=False)
    except OSError:
        same = False
    if same:
        rprint(
            "[red]ERROR:[/red] In-place overwrite is not allowed "
            "(the source file would be destroyed). Specify a different --out path."
        )
        raise typer.Exit(1)


def _check_diagnostics_or_exit(diagnostics: list[DiagnosticEntry]) -> None:
    """Print error diagnostics and exit 1 if any exist."""
    errors = [d for d in diagnostics if d.level == "error"]
    if errors:
        for e in errors:
            rprint(f"[red]ERROR:[/red] {e.message}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
