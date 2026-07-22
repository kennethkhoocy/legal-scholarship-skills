"""Unpack a .docx for the unpack→Edit→pack workflow (Anthropic office/unpack.py)."""

from __future__ import annotations

import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from anthropic_bridge import AnthropicSkillNotInstalledError, run_anthropic


def run(input_path: Path, out_dir: Path, merge_runs: bool = True) -> int:
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    args = [str(input_path), str(out_dir)]
    if not merge_runs:
        args.extend(["--merge-runs", "false"])
    try:
        result = run_anthropic("office/unpack.py", *args, check=False)
    except AnthropicSkillNotInstalledError as e:
        print(str(e), file=sys.stderr)
        return 2
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode
