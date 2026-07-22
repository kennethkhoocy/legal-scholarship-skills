"""Thin CLI wrappers that delegate to Anthropic's docx-skill scripts.

Each module exposes a single `run(...)` function and is wired into
word_docx.py as a typer subcommand. None of these modules import or
copy Anthropic source; they only invoke installed scripts via
anthropic_bridge.run_anthropic.
"""
