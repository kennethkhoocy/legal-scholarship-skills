#!/usr/bin/env python3
"""
Test short_form.py across all 5 citation styles.

Creates a synthetic .tex with repeated citations, runs short_form.py
with each style, and checks that the correct short-form terms appear.
"""

import sys
import tempfile
from pathlib import Path

SKILL_DIR = str(Path(__file__).parent.parent)
sys.path.insert(0, str(Path(SKILL_DIR) / "scripts"))

from short_form import process

SAMPLE_TEX = r"""
\documentclass{article}
\begin{document}

\section{Introduction}

Some claim about governance.\footnote{See Jeffrey N. Gordon, \textit{The Rise of Independent Directors in the United States, 1950--2005}, 59 \textsc{Stan.\ L.\ Rev.}\ 1465 (2007) (tracing the rise of independent directors).}

Another related point.\footnote{See Lucian A. Bebchuk \& Jesse M. Fried, \textit{Pay Without Performance: The Unfulfilled Promise of Executive Compensation}, 59 \textsc{Stan.\ L.\ Rev.}\ 100 (2004) (arguing that pay reflects managerial power).}

\section{Analysis}

Returning to the governance point.\footnote{See Jeffrey N. Gordon, \textit{The Rise of Independent Directors in the United States, 1950--2005}, 59 \textsc{Stan.\ L.\ Rev.}\ 1465 (2007) (tracing the rise of independent directors).}

Same source immediately after.\footnote{See Jeffrey N. Gordon, \textit{The Rise of Independent Directors in the United States, 1950--2005}, 59 \textsc{Stan.\ L.\ Rev.}\ 1465 (2007) (tracing the rise of independent directors).}

Back to Bebchuk.\footnote{See Lucian A. Bebchuk \& Jesse M. Fried, \textit{Pay Without Performance: The Unfulfilled Promise of Executive Compensation}, 59 \textsc{Stan.\ L.\ Rev.}\ 100 (2004) (arguing that pay reflects managerial power).}

\end{document}
"""

EXPECTED = {
    "bluebook": {
        "must_contain": [r"\textit{Id.}", r"\textit{supra} note"],
        "must_not_contain": ["ibid", "Ibid.", "(n "],
    },
    "oscola": {
        "must_contain": ["ibid", "(n "],
        "must_not_contain": [r"\textit{Id.}", r"\textit{supra}"],
    },
    "chicago": {
        "must_contain": ["Ibid."],
        "must_not_contain": [r"\textit{Id.}", r"\textit{supra} note", "ibid"],
    },
    "apa": {
        "must_contain": [],  # APA has no ibid; uses author-year repeat
        "must_not_contain": [r"\textit{Id.}", "ibid", "Ibid."],
    },
    "mcgill": {
        "must_contain": [r"\textit{Ibid}", "supra note"],
        "must_not_contain": [r"\textit{Id.}", "(n "],
    },
}


def run_test(style_id: str) -> tuple[bool, str]:
    """Run short_form.py with the given style and check output."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".tex", delete=False, encoding="utf-8"
    ) as f:
        f.write(SAMPLE_TEX)
        input_path = f.name

    output_path = input_path.replace(".tex", f"_{style_id}.tex")

    try:
        process(input_path, output_path, style_id=style_id, skill_dir=SKILL_DIR)
        result = Path(output_path).read_text(encoding="utf-8")

        errors = []
        for pattern in EXPECTED[style_id]["must_contain"]:
            if pattern not in result:
                errors.append(f"MISSING: '{pattern}'")

        for pattern in EXPECTED[style_id]["must_not_contain"]:
            if pattern in result:
                errors.append(f"UNEXPECTED: '{pattern}'")

        if errors:
            return False, "; ".join(errors)
        return True, "OK"

    except Exception as e:
        return False, str(e)
    finally:
        Path(input_path).unlink(missing_ok=True)
        Path(output_path).unlink(missing_ok=True)


def main():
    print("=" * 60)
    print("Testing short_form.py across 5 citation styles")
    print("=" * 60)

    all_passed = True
    for style_id in ["bluebook", "oscola", "chicago", "apa", "mcgill"]:
        passed, msg = run_test(style_id)
        status = "PASS" if passed else "FAIL"
        print(f"  {style_id:10s}: {status} — {msg}")
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
