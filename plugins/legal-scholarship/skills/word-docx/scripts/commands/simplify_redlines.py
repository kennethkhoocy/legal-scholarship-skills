"""Simplify noisy redline markup via Anthropic's office/helpers/simplify_redlines.py.

The upstream helper operates on an unpacked directory, not a .docx file directly.
This wrapper handles the unpack -> simplify -> repack pipeline internally so the
CLI surface remains the conventional (input_docx, output_docx) two-argument form.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from anthropic_bridge import AnthropicSkillNotInstalledError, run_anthropic, resolve_anthropic_docx


def run(input_path: Path, out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        skill_root = resolve_anthropic_docx()
    except AnthropicSkillNotInstalledError as e:
        print(str(e), file=sys.stderr)
        return 2

    # Unpack, simplify in-place on the unpacked dir, then repack.
    with tempfile.TemporaryDirectory() as tmp_dir:
        unpacked = Path(tmp_dir) / "unpacked"

        # Step 1: unpack
        unpack_result = run_anthropic(
            "office/unpack.py",
            str(input_path),
            str(unpacked),
            check=False,
        )
        if unpack_result.returncode != 0:
            if unpack_result.stderr:
                print(unpack_result.stderr, file=sys.stderr)
            return unpack_result.returncode

        # Step 2: simplify redlines in the unpacked directory (library call, no CLI)
        helpers_path = skill_root / "scripts" / "office" / "helpers"
        helpers_str = str(helpers_path)
        if helpers_str not in sys.path:
            sys.path.insert(0, helpers_str)

        try:
            from simplify_redlines import simplify_redlines  # type: ignore[import]
            count, message = simplify_redlines(str(unpacked))
            print(message)
        except Exception as e:
            print(f"Error during simplification: {e}", file=sys.stderr)
            return 1

        # Step 3: repack
        pack_result = run_anthropic(
            "office/pack.py",
            str(unpacked),
            str(out_path),
            "--original", str(input_path),
            check=False,
        )
        if pack_result.stdout:
            print(pack_result.stdout)
        if pack_result.stderr:
            print(pack_result.stderr, file=sys.stderr)
        return pack_result.returncode
