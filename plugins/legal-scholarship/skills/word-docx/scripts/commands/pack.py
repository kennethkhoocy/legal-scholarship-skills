"""Repack an unpacked directory back into a .docx (Anthropic office/pack.py)."""

from __future__ import annotations

import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from anthropic_bridge import AnthropicSkillNotInstalledError, run_anthropic


def run(unpacked_dir: Path, out_path: Path, original: Path | None = None, validate: bool = True) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    args = [str(unpacked_dir), str(out_path)]
    if original is not None:
        args.extend(["--original", str(original)])
    if not validate:
        args.extend(["--validate", "false"])
    try:
        result = run_anthropic("office/pack.py", *args, check=False)
    except AnthropicSkillNotInstalledError as e:
        print(str(e), file=sys.stderr)
        return 2
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode
