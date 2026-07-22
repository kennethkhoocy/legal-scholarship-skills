"""Locator + subprocess helper for Anthropic's installed docx skill.

Resolves the path to the docx skill scripts inside the
`document-skills@anthropic-agent-skills` plugin. Does not copy any of
Anthropic's code into word-docx; every operation is a subprocess to the
plugin's existing scripts.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_INSTALL_INSTRUCTIONS = (
    "Anthropic's docx skill is not installed. Install it with:\n"
    "  claude plugin marketplace add anthropics/skills\n"
    "  claude plugin install document-skills@anthropic-agent-skills"
)


class AnthropicSkillNotInstalledError(RuntimeError):
    """Raised when the Anthropic docx skill cannot be resolved on disk."""

    def __init__(self, detail: str = "") -> None:
        message = _INSTALL_INSTRUCTIONS
        if detail:
            message = f"{detail}\n\n{message}"
        super().__init__(message)


def _is_valid_skill_dir(path: Path) -> bool:
    return (path / "SKILL.md").is_file() and (path / "scripts").is_dir()


def _plugin_cache_candidates() -> list[Path]:
    base = Path.home() / ".claude" / "plugins" / "cache" / "anthropic-agent-skills" / "document-skills"
    if not base.is_dir():
        return []
    versioned = sorted(
        (p for p in base.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [p / "skills" / "docx" for p in versioned]


def _fallback_candidates() -> list[Path]:
    return [Path.home() / ".claude" / "skills" / "docx"]


def resolve_anthropic_docx() -> Path:
    env_path = os.environ.get("ANTHROPIC_DOCX_PATH")
    if env_path:
        candidate = Path(env_path)
        if _is_valid_skill_dir(candidate):
            return candidate
    for candidate in _plugin_cache_candidates():
        if _is_valid_skill_dir(candidate):
            return candidate
    for candidate in _fallback_candidates():
        if _is_valid_skill_dir(candidate):
            return candidate
    raise AnthropicSkillNotInstalledError()


def anthropic_script(name: str) -> Path:
    """Resolve a script relative to the docx skill's scripts/ directory.

    Example: anthropic_script("office/unpack.py")
    """
    base = resolve_anthropic_docx()
    path = base / "scripts" / name
    if not path.is_file():
        raise AnthropicSkillNotInstalledError(
            f"Resolved docx skill at {base}, but {path} is missing."
        )
    return path


def run_anthropic(
    name: str,
    *args: str,
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
    **kwargs,
) -> subprocess.CompletedProcess:
    """Shell out to an Anthropic docx script via the current Python interpreter."""
    script = anthropic_script(name)
    cmd = [sys.executable, str(script), *args]
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture_output,
        text=text,
        **kwargs,
    )
