"""Convert legacy .doc to .docx via Anthropic's office/soffice.py wrapper."""

from __future__ import annotations

import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from anthropic_bridge import AnthropicSkillNotInstalledError, run_anthropic


def run(input_path: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = run_anthropic(
            "office/soffice.py",
            "--headless",
            "--convert-to",
            "docx",
            "--outdir",
            str(out_dir),
            str(input_path),
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
