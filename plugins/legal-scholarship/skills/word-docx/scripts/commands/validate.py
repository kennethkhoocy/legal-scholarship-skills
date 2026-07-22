"""Validate a .docx via Anthropic's office/validate.py (schema + auto-repair)."""

from __future__ import annotations

import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from anthropic_bridge import AnthropicSkillNotInstalledError, run_anthropic


def run(input_path: Path) -> int:
    """Return the validator's exit code; surface its stdout/stderr."""
    try:
        result = run_anthropic("office/validate.py", str(input_path), check=False)
    except AnthropicSkillNotInstalledError as e:
        print(str(e), file=sys.stderr)
        return 2
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode
