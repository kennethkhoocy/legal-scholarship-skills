from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import fitz


NUMBER_RE = r"\d[\d.,]*\d|\d"
TOKEN_RE = re.compile(rf"{NUMBER_RE}|[^\W\d_]+", re.UNICODE)
LABELS = ("Table", "Figure", "Equation")
SPURIOUS_MARKERS = (
    r"\cref",
    r"\Cref",
    r"\textit",
    r"\textbf",
    r"\begin",
    r"\includegraphics",
    r"\sym",
    r"\footnote",
    r"\multicolumn",
    r"\multirow",
    r"\toprule",
    r"\cmidrule",
    "%%TABLE",
    "%%FIGURE",
    "%%PAGEBREAK",
    "$",
    "^{",
    "_{",
)

MISSING_OK_LT_PCT = 3.0
MAX_MISSING_NUMBERS = 20
MAX_SPURIOUS_SAMPLES = 10
MAX_MISSING_TOKEN_SAMPLES = 50


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_pdf_text(path: Path) -> tuple[str, list[str]]:
    errors: list[str] = []
    chunks: list[str] = []

    try:
        doc = fitz.open(str(path))
    except Exception as exc:  # noqa: BLE001 - per-test robustness matters here.
        return "", [f"open failed for {path.name}: {exc}"]

    try:
        for page_index in range(doc.page_count):
            try:
                chunks.append(doc.load_page(page_index).get_text())
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{path.name} page {page_index + 1} text failed: {exc}")
    finally:
        doc.close()

    return normalize_whitespace("\n".join(chunks)), errors


def tokenize_significant(text: str) -> tuple[list[str], list[str], list[str]]:
    tokens: list[str] = []
    numbers: list[str] = []
    words: list[str] = []

    for match in TOKEN_RE.finditer(text):
        value = match.group(0)
        if value[0].isdigit():
            tokens.append(value)
            numbers.append(value)
            continue
        if len(value) >= 3 and value.isalpha():
            word = value.casefold()
            tokens.append(word)
            words.append(word)

    return tokens, numbers, words


def first_positions(items: list[str]) -> dict[str, int]:
    positions: dict[str, int] = {}
    for index, item in enumerate(items):
        positions.setdefault(item, index)
    return positions


def ranked_missing(items: list[str], missing: set[str], limit: int) -> list[str]:
    counts = Counter(items)
    positions = first_positions(items)
    ranked = sorted(missing, key=lambda item: (-counts[item], positions.get(item, sys.maxsize), item))
    return ranked[:limit]


def count_labels(text: str) -> dict[str, int]:
    return {label: len(re.findall(rf"\b{re.escape(label)}\b", text)) for label in LABELS}


def find_spurious_latex(text: str, compiled_text: str = "") -> dict[str, Any]:
    marker_counts: dict[str, int] = {}
    compiled_marker_counts: dict[str, int] = {}
    samples: list[str] = []
    total = 0

    for marker in SPURIOUS_MARKERS:
        converted_count = text.count(marker)
        if converted_count == 0:
            continue

        compiled_count = compiled_text.count(marker) if compiled_text else 0
        count = max(0, converted_count - compiled_count)
        if count == 0:
            if compiled_count:
                compiled_marker_counts[marker] = min(converted_count, compiled_count)
            continue

        marker_counts[marker] = count
        if compiled_count:
            compiled_marker_counts[marker] = min(converted_count, compiled_count)
        total += count

        start = 0
        skipped = 0
        while len(samples) < MAX_SPURIOUS_SAMPLES:
            index = text.find(marker, start)
            if index < 0:
                break
            if skipped < compiled_count:
                skipped += 1
                start = index + max(1, len(marker))
                continue
            context_start = max(0, index - 35)
            context_end = min(len(text), index + len(marker) + 35)
            samples.append(text[context_start:context_end].strip())
            start = index + max(1, len(marker))

    return {
        "count": total,
        "markers": marker_counts,
        "compiled_literal_markers": compiled_marker_counts,
        "samples": samples,
    }


def load_index(index_path: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if not index_path.exists():
        return {}, [f"{index_path.name} not found"]

    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {}, [f"{index_path.name} could not be read: {exc}"]

    tests = data.get("tests", [])
    if not isinstance(tests, list):
        return {}, [f"{index_path.name} has no list-valued tests field"]

    by_name: dict[str, dict[str, Any]] = {}
    for item in tests:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            by_name[item["name"]] = item
    return by_name, []


def to_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def stdout_count(stdout: str, label: str) -> int | None:
    match = re.search(rf"^{re.escape(label)}:\s*(\d+)\s*$", stdout, re.MULTILINE)
    return int(match.group(1)) if match else None


def first_present(*values: Any, default: int = 0) -> int:
    for value in values:
        if value is not None:
            return to_int(value, default)
    return default


def convert_summary(test_index_entry: dict[str, Any] | None) -> dict[str, Any]:
    summary = (test_index_entry or {}).get("convert_summary", {})
    if not isinstance(summary, dict):
        summary = {}

    json_summary = summary.get("json", {})
    if not isinstance(json_summary, dict):
        json_summary = {}

    tables = summary.get("tables", {})
    if not isinstance(tables, dict):
        tables = {}

    figures = summary.get("figures", {})
    if not isinstance(figures, dict):
        figures = {}

    stdout = summary.get("stdout", "")
    if not isinstance(stdout, str):
        stdout = ""

    detected_tables = first_present(
        tables.get("detected"),
        json_summary.get("tables_detected"),
        stdout_count(stdout, "Tables detected"),
    )
    inserted_tables = first_present(
        tables.get("inserted"),
        json_summary.get("tables_inserted"),
        stdout_count(stdout, "Tables inserted"),
    )
    detected_figures = first_present(
        figures.get("detected"),
        json_summary.get("figures_detected"),
        stdout_count(stdout, "Figures detected"),
    )
    inserted_figures = first_present(
        figures.get("inserted"),
        json_summary.get("figures_inserted"),
        stdout_count(stdout, "Figures inserted"),
    )

    unresolved = first_present(
        summary.get("unresolved"),
        json_summary.get("unresolved"),
        stdout_count(stdout, "Unresolved placeholders"),
    )
    refs = first_present(
        summary.get("refs"),
        json_summary.get("refs"),
        stdout_count(stdout, "Unresolved reference commands"),
    )

    return {
        "returncode": summary.get("returncode"),
        "tables": {
            "detected": detected_tables,
            "inserted": inserted_tables,
        },
        "figures": {
            "detected": detected_figures,
            "inserted": inserted_figures,
        },
        "footnotes": first_present(
            summary.get("footnotes"),
            json_summary.get("footnotes"),
            stdout_count(stdout, "Footnotes"),
        ),
        "equations": first_present(
            summary.get("equations"),
            json_summary.get("equations"),
            stdout_count(stdout, "OMML equations"),
        ),
        "unresolved": unresolved,
        "refs": refs,
        "unresolved_total": unresolved + refs,
        "errors": summary.get("errors", []) if isinstance(summary.get("errors"), list) else [],
        "present": bool(summary),
    }


def build_test_result(test_dir: Path, index_entry: dict[str, Any] | None) -> dict[str, Any]:
    name = test_dir.name
    compiled_pdf = test_dir / f"{name}_compiled.pdf"
    converted_pdf = test_dir / f"{name}_converted.pdf"
    errors: list[str] = []

    compiled_text, compiled_errors = extract_pdf_text(compiled_pdf)
    converted_text, converted_errors = extract_pdf_text(converted_pdf)
    errors.extend(compiled_errors)
    errors.extend(converted_errors)

    compiled_tokens, compiled_numbers, compiled_words = tokenize_significant(compiled_text)
    converted_tokens, converted_numbers, converted_words = tokenize_significant(converted_text)

    compiled_set = set(compiled_tokens)
    converted_set = set(converted_tokens)
    missing = compiled_set - converted_set
    missing_fraction = len(missing) / len(compiled_set) if compiled_set else 0.0
    missing_pct = missing_fraction * 100.0

    compiled_number_set = set(compiled_numbers)
    converted_number_set = set(converted_numbers)
    missing_number_set = compiled_number_set - converted_number_set

    summary = convert_summary(index_entry)
    spurious = find_spurious_latex(converted_text, compiled_text)
    unresolved_total = to_int(summary.get("unresolved_total"))
    verdict = (
        "OK"
        if missing_pct < MISSING_OK_LT_PCT
        and spurious["count"] == 0
        and unresolved_total == 0
        and not errors
        else "FLAG"
    )

    return {
        "name": name,
        "verdict": verdict,
        "compiled_pdf": str(compiled_pdf),
        "converted_pdf": str(converted_pdf),
        "missing_pct": round(missing_pct, 4),
        "missing_fraction": round(missing_fraction, 6),
        "missing_tokens": {
            "count": len(missing),
            "samples": ranked_missing(compiled_tokens, missing, MAX_MISSING_TOKEN_SAMPLES),
        },
        "missing_numbers": ranked_missing(compiled_numbers, missing_number_set, MAX_MISSING_NUMBERS),
        "missing_numbers_count": len(missing_number_set),
        "spurious_latex": spurious,
        "label_counts": {
            "compiled": count_labels(compiled_text),
            "converted": count_labels(converted_text),
        },
        "convert_summary": summary,
        "token_counts": {
            "compiled_significant_distinct": len(compiled_set),
            "converted_significant_distinct": len(converted_set),
            "compiled_significant_total": len(compiled_tokens),
            "converted_significant_total": len(converted_tokens),
            "compiled_numbers_distinct": len(compiled_number_set),
            "converted_numbers_distinct": len(converted_number_set),
            "compiled_words_distinct": len(set(compiled_words)),
            "converted_words_distinct": len(set(converted_words)),
        },
        "text_chars": {
            "compiled": len(compiled_text),
            "converted": len(converted_text),
        },
        "errors": errors,
    }


def discover_test_dirs(tests_dir: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in tests_dir.iterdir()
            if path.is_dir() and re.match(r"^t\d+", path.name)
        ),
        key=lambda path: path.name,
    )


def has_both_pdfs(test_dir: Path) -> bool:
    name = test_dir.name
    return (test_dir / f"{name}_compiled.pdf").exists() and (test_dir / f"{name}_converted.pdf").exists()


def row_value(result: dict[str, Any]) -> list[str]:
    summary = result["convert_summary"]
    tables = summary["tables"]
    figures = summary["figures"]
    top_numbers = ", ".join(result["missing_numbers"][:MAX_MISSING_NUMBERS])
    if not top_numbers:
        top_numbers = "-"

    return [
        result["name"],
        result["verdict"],
        f"{result['missing_pct']:.2f}",
        str(result["spurious_latex"]["count"]),
        f"{tables['inserted']}/{tables['detected']}",
        f"{figures['inserted']}/{figures['detected']}",
        str(summary["equations"]),
        str(summary["unresolved_total"]),
        top_numbers,
    ]


def print_table(results: list[dict[str, Any]], skipped: list[dict[str, str]]) -> None:
    headers = [
        "name",
        "verdict",
        "missing%",
        "spurious",
        "tbl(conv/det)",
        "fig(conv/det)",
        "eqn",
        "unres",
        "top missing numbers",
    ]
    rows = [row_value(result) for result in results]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows)) if rows else len(headers[index])
        for index in range(len(headers))
    ]

    def format_row(row: list[str]) -> str:
        return " | ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    print(format_row(headers))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(format_row(row))

    if skipped:
        skipped_names = ", ".join(item["name"] for item in skipped)
        print(f"Skipped missing PDF pairs: {skipped_names}")


def main() -> int:
    tests_dir = Path(__file__).parent.absolute()
    index_by_name, index_errors = load_index(tests_dir / "index.json")
    skipped: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []

    for test_dir in discover_test_dirs(tests_dir):
        if not has_both_pdfs(test_dir):
            skipped.append({"name": test_dir.name, "reason": "missing compiled or converted PDF"})
            continue

        try:
            results.append(build_test_result(test_dir, index_by_name.get(test_dir.name)))
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "name": test_dir.name,
                    "verdict": "FLAG",
                    "compiled_pdf": str(test_dir / f"{test_dir.name}_compiled.pdf"),
                    "converted_pdf": str(test_dir / f"{test_dir.name}_converted.pdf"),
                    "missing_pct": 100.0,
                    "missing_fraction": 1.0,
                    "missing_tokens": {"count": 0, "samples": []},
                    "missing_numbers": [],
                    "missing_numbers_count": 0,
                    "spurious_latex": {"count": 0, "markers": {}, "compiled_literal_markers": {}, "samples": []},
                    "label_counts": {"compiled": {}, "converted": {}},
                    "convert_summary": convert_summary(index_by_name.get(test_dir.name)),
                    "token_counts": {},
                    "text_chars": {},
                    "errors": [f"test failed: {exc}"],
                }
            )

    report = {
        "tests_dir": str(tests_dir),
        "thresholds": {
            "ok_missing_pct_lt": MISSING_OK_LT_PCT,
            "ok_spurious_latex_eq": 0,
            "ok_unresolved_total_eq": 0,
        },
        "index_errors": index_errors,
        "skipped": skipped,
        "tests": results,
    }

    output_path = tests_dir / "qa_metrics.json"
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print_table(results, skipped)
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
