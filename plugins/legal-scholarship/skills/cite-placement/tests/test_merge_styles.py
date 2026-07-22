#!/usr/bin/env python3
"""
Test merge_adjacent_footnotes.py across styles.
Verifies that OSCOLA merges produce no trailing period, while Bluebook does.
"""

import sys
import tempfile
from pathlib import Path

SKILL_DIR = str(Path(__file__).parent.parent)
sys.path.insert(0, str(Path(SKILL_DIR) / "scripts"))

from merge_adjacent_footnotes import process

SAMPLE_TEX = r"""\documentclass{article}
\begin{document}

Some text.\footnote{See Author A, \textit{Title A}, 59 \textsc{J.\ Fin.}\ 100 (2020) (finding X).}\footnote{See also Author B, \textit{Title B}, 30 \textsc{Rev.\ Fin.\ Stud.}\ 200 (2021) (showing Y).}

\end{document}
"""


def run_test(style_id: str, expect_period: bool) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".tex", delete=False, encoding="utf-8"
    ) as f:
        f.write(SAMPLE_TEX)
        path = f.name

    try:
        process(path, path, style=style_id, skill_dir=SKILL_DIR)
        result = Path(path).read_text(encoding="utf-8")

        fn_count = result.count(r"\footnote{")
        if fn_count != 1:
            return False, f"Expected 1 merged footnote, got {fn_count}"

        # Use brace-depth parser to extract footnote content
        idx = result.index(r"\footnote{")
        start = idx + len(r"\footnote{")
        depth = 1
        pos = start
        while pos < len(result) and depth > 0:
            if result[pos] == "{":
                depth += 1
            elif result[pos] == "}":
                depth -= 1
            pos += 1
        content = result[start:pos - 1].strip()
        ends_with_period = content.endswith(".")

        if expect_period and not ends_with_period:
            return False, f"Expected trailing period, got: ...{content[-20:]}"
        if not expect_period and ends_with_period:
            return False, f"Expected NO trailing period, got: ...{content[-20:]}"

        if "; " not in content:
            return False, "Missing semicolon separator in merged footnote"

        return True, "OK"
    finally:
        Path(path).unlink(missing_ok=True)


def main():
    print("=" * 60)
    print("Testing merge_adjacent_footnotes.py across styles")
    print("=" * 60)

    tests = [
        ("bluebook", True),
        ("oscola", False),
        ("chicago", True),
        ("apa", True),
        ("mcgill", True),
    ]

    all_passed = True
    for style_id, expect_period in tests:
        passed, msg = run_test(style_id, expect_period)
        status = "PASS" if passed else "FAIL"
        period_label = "with period" if expect_period else "no period"
        print(f"  {style_id:10s} ({period_label:10s}): {status} — {msg}")
        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("All tests passed.")
    else:
        print("Some tests FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
