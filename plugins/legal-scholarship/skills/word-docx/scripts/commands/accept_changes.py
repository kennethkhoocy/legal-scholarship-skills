"""Accept all tracked changes via Anthropic's accept_changes.py (LibreOffice)."""

from __future__ import annotations

import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from anthropic_bridge import AnthropicSkillNotInstalledError, run_anthropic


def run(input_path: Path, out_path: Path) -> int:
    try:
        result = run_anthropic(
            "accept_changes.py",
            str(input_path),
            str(out_path),
            check=False,
        )
    except AnthropicSkillNotInstalledError as e:
        print(str(e), file=sys.stderr)
        return 2
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode
