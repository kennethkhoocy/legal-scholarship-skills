"""Standalone citation restyle app — converts footnote styles in .docx files.

Double-click to run. Requires an Anthropic API key (entered on first run
or set via ANTHROPIC_API_KEY environment variable).

No Claude Code, no Python installation needed (when distributed as .exe).
"""

import json
import os
import re
import shutil
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# ── Resolve paths (works both as .py and as PyInstaller .exe) ─────────

if getattr(sys, "frozen", False):
    _BUNDLE_DIR = Path(sys._MEIPASS)
    _STYLES_DIR = _BUNDLE_DIR / "styles"
    _CORE_DIR = _BUNDLE_DIR
else:
    _SKILL_ROOT = Path(__file__).resolve().parents[2]
    _STYLES_DIR = _SKILL_ROOT / "references" / "styles"
    _CORE_DIR = _SKILL_ROOT / "scripts" / "core"
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

# ── API key management ────────────────────────────────────────────────

_CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "cite-restyle"
_CONFIG_FILE = _CONFIG_DIR / "config.json"


def _load_api_key() -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    if _CONFIG_FILE.is_file():
        try:
            cfg = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            return cfg.get("api_key")
        except Exception:
            pass
    return None


def _save_api_key(key: str):
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps({"api_key": key}), encoding="utf-8")


def _prompt_api_key(parent) -> str | None:
    dialog = tk.Toplevel(parent)
    dialog.title("Anthropic API Key")
    dialog.geometry("480x180")
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()

    ttk.Label(dialog, text="Enter your Anthropic API key:", font=("", 10)).pack(pady=(15, 5))
    ttk.Label(dialog, text="Get one at console.anthropic.com", font=("", 8)).pack()

    key_var = tk.StringVar()
    entry = ttk.Entry(dialog, textvariable=key_var, width=55, show="*")
    entry.pack(pady=10, padx=20)
    entry.focus_set()

    result = [None]

    def on_ok():
        k = key_var.get().strip()
        if k.startswith("sk-"):
            result[0] = k
            _save_api_key(k)
            dialog.destroy()
        else:
            messagebox.showerror("Invalid key", "API key should start with 'sk-'", parent=dialog)

    def on_cancel():
        dialog.destroy()

    btn_frame = ttk.Frame(dialog)
    btn_frame.pack(pady=5)
    ttk.Button(btn_frame, text="OK", command=on_ok).pack(side="left", padx=5)
    ttk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side="left", padx=5)

    entry.bind("<Return>", lambda e: on_ok())
    dialog.wait_window()
    return result[0]


# ── Style definitions ─────────────────────────────────────────────────

STYLE_OPTIONS = [
    "Bluebook (21st ed.)",
    "OSCOLA (4th ed.)",
    "Chicago (17th ed., notes-bib)",
    "APA (7th ed.)",
    "McGill Guide (9th ed.)",
]
STYLE_IDS = ["bluebook", "oscola", "chicago", "apa", "mcgill"]


def _load_style_md(style_id: str) -> str:
    p = _STYLES_DIR / f"{style_id}.md"
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return f"(Style file not found: {p})"


# ── LLM restyle engine ───────────────────────────────────────────────

def _call_llm(prompt: str, api_key: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _build_prompt(footnotes_batch, current_style, target_style, display_map):
    current_md = _load_style_md(current_style)
    target_md = _load_style_md(target_style)
    offset = display_map.get("offset", 0)

    fn_list = ""
    for fn in footnotes_batch:
        disp = display_map["id_to_display"].get(fn["footnote_id"], "?")
        fn_list += f"\n[FN {disp}] {fn['text']}\n"

    return f"""You are restyling footnote citations from {current_style.upper()} to {target_style.upper()}.

## Current citation style rules
{current_md}

## Target citation style rules
{target_md}

## Footnote numbering
This document has {offset} symbol footnote(s) before the numbered footnotes.
Cross-references like "supra note N" use OOXML IDs. Subtract {offset} from each referenced number.

## Footnotes to restyle
{fn_list}

## Instructions
For each footnote, output a JSON array. Each element:
- "display": displayed footnote number (string)
- "new_text": restyled content in {target_style.upper()} format as plain text. Use *italic* markers ONLY for book titles. Do NOT use **bold** markers — no citation style uses bold in footnotes. Journal names, author names, and all other text should be unformatted plain text.
- "skipped": true if the footnote should not be restyled (discursive, contact info, case citations, legislation)

Rules:
1. Reformat each academic citation per the target style rules.
2. Convert cross-references (supra note N → target convention like (n N)), adjusting numbers by offset.
3. Convert Id./ibid to target equivalent.
4. Convert Infra/Supra Part references to target convention (eg "see Part X below/above" for OSCOLA).
5. Remove signals (See, See also, See generally, Cf., etc.) if target style doesn't use them.
6. Preserve discursive text unchanged.
7. Multi-citation footnotes: restyle each citation, keep semicolon separation.
8. MIXED footnotes containing BOTH case citations AND academic citations: preserve the case citations unchanged but STILL convert the academic parts (cross-references, signals, author formatting). Do NOT skip the entire footnote just because it contains a case citation.
9. Every footnote in the batch MUST appear in the output JSON — either with new_text or with skipped:true. Do not omit any.

Output ONLY the JSON array."""


def _parse_response(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    # First try standard parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fix common LLM JSON issues
    fixed = text
    fixed = re.sub(r",\s*([}\]])", r"\1", fixed)  # trailing commas
    fixed = fixed.replace("\n", " ")  # newlines inside strings
    fixed = re.sub(r'(?<!\\)"(?=\w)', '\\"', fixed)  # unescaped internal quotes (heuristic)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    # Last resort: extract individual JSON objects
    results = []
    for m in re.finditer(r'\{[^{}]*"display"\s*:\s*"[^"]*"[^{}]*\}', text):
        try:
            results.append(json.loads(m.group()))
        except json.JSONDecodeError:
            continue
    if results:
        return results
    raise ValueError(f"Could not parse LLM response as JSON: {text[:200]}...")


BATCH_SIZE = 25


def restyle_docx(input_path, output_path, current_style, target_style,
                 api_key, progress_callback=None):
    """Run the full .docx restyle pipeline via Claude API."""
    from docx_support.footnotes import (
        build_display_number_map, copy_docx,
        extract_footnotes_with_formatting, replace_footnote_text,
    )
    from docx_support.audit_ooxml import validate_docx

    def _log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg)

    input_path = Path(input_path)
    output_path = Path(output_path)

    copy_docx(input_path, output_path)
    _log(f"Copied to {output_path.name}")

    diags = validate_docx(output_path)
    if any(d.level == "error" for d in diags):
        return {"error": "Invalid .docx file", "changed": 0, "total": 0}

    display_map = build_display_number_map(output_path)
    _log(f"Display offset: {display_map['offset']} symbol footnote(s)")

    footnotes = extract_footnotes_with_formatting(output_path)
    _log(f"Extracted {len(footnotes)} footnotes")

    changelog = []
    errors = 0
    changed = 0
    skipped = 0
    total_batches = (len(footnotes) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(footnotes))
        batch = footnotes[start:end]

        _log(f"Batch {batch_idx + 1}/{total_batches}: footnotes {start + 1}–{end} (calling Claude...)")

        prompt = _build_prompt(batch, current_style, target_style, display_map)

        results = None
        for attempt in range(3):
            try:
                response_text = _call_llm(prompt, api_key)
                results = _parse_response(response_text)
                break
            except Exception as e:
                if attempt < 2:
                    _log(f"  Attempt {attempt + 1} failed ({e}), retrying...")
                else:
                    _log(f"  API error after 3 attempts: {e}")
                    errors += len(batch)

        if results is None:
            continue

        result_map = {str(r.get("display", "")): r for r in results}

        for fn in batch:
            fn_id = fn["footnote_id"]
            disp = str(display_map["id_to_display"].get(fn_id, "?"))
            r = result_map.get(disp)

            if not r:
                skipped += 1
                continue
            if r.get("skipped"):
                skipped += 1
                continue

            new_text = r.get("new_text", "")
            if not new_text or new_text == fn["text"]:
                skipped += 1
                continue

            try:
                ok = replace_footnote_text(output_path, fn_id, new_text)
            except Exception as e:
                _log(f"  Write error FN {disp}: {e}")
                errors += 1
                continue
            if ok:
                changed += 1
                changelog.append({"fn_id": fn_id, "display": disp,
                                  "old": fn["text"][:80], "new": new_text[:80]})
            else:
                _log(f"  Replace failed FN {disp} (id={fn_id})")
                errors += 1

    log_path = output_path.parent / "restyle_changelog.json"
    log_path.write_text(json.dumps(changelog, indent=2, ensure_ascii=False), encoding="utf-8")

    _log(f"\nDone: {changed} converted, {skipped} skipped, {errors} errors")
    _log(f"Output: {output_path}")

    return {"output_path": str(output_path), "total": len(footnotes),
            "changed": changed, "skipped": skipped, "errors": errors,
            "changelog_path": str(log_path)}


# ── GUI ───────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    root.title("Citation Restyle Tool")
    root.resizable(True, False)

    outer = ttk.Frame(root, padding=12)
    outer.grid(sticky="nsew")
    root.columnconfigure(0, weight=1)
    outer.columnconfigure(0, weight=1)

    # ── Files ──
    file_frame = ttk.LabelFrame(outer, text="Files", padding=8)
    file_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    file_frame.columnconfigure(1, weight=1)

    ttk.Label(file_frame, text="Input .docx:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
    input_entry = ttk.Entry(file_frame, width=55)
    input_entry.grid(row=0, column=1, sticky="ew", pady=3)

    def browse_input():
        f = filedialog.askopenfilename(title="Select Input Manuscript",
            filetypes=[("Word documents", "*.docx"), ("All files", "*.*")])
        if f:
            input_entry.delete(0, tk.END)
            input_entry.insert(0, f)
            p = Path(f)
            output_entry.delete(0, tk.END)
            output_entry.insert(0, str(p.parent / f"{p.stem}_restyled.docx"))

    ttk.Button(file_frame, text="Browse...", command=browse_input).grid(row=0, column=2, padx=(4, 0))

    ttk.Label(file_frame, text="Output .docx:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
    output_entry = ttk.Entry(file_frame, width=55)
    output_entry.grid(row=1, column=1, sticky="ew", pady=3)

    def browse_output():
        f = filedialog.asksaveasfilename(title="Select Output File",
            filetypes=[("Word documents", "*.docx")], defaultextension=".docx")
        if f:
            output_entry.delete(0, tk.END)
            output_entry.insert(0, f)

    ttk.Button(file_frame, text="Browse...", command=browse_output).grid(row=1, column=2, padx=(4, 0))

    # ── Style selection ──
    style_frame = ttk.LabelFrame(outer, text="Citation Style Conversion", padding=8)
    style_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    style_frame.columnconfigure(1, weight=1)

    ttk.Label(style_frame, text="From:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
    from_combo = ttk.Combobox(style_frame, values=STYLE_OPTIONS, state="readonly", width=30)
    from_combo.set(STYLE_OPTIONS[0])
    from_combo.grid(row=0, column=1, sticky="w", pady=3)

    ttk.Label(style_frame, text="To:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
    to_combo = ttk.Combobox(style_frame, values=STYLE_OPTIONS, state="readonly", width=30)
    to_combo.set(STYLE_OPTIONS[1])
    to_combo.grid(row=1, column=1, sticky="w", pady=3)

    # ── Buttons ──
    btn_frame = ttk.Frame(outer)
    btn_frame.grid(row=2, column=0, sticky="e", pady=(4, 0))

    def on_restyle():
        inp = input_entry.get().strip()
        out = output_entry.get().strip()
        if not inp or not Path(inp).is_file():
            messagebox.showerror("Error", "Select a valid input .docx file.")
            return
        if not out:
            messagebox.showerror("Error", "Specify an output file.")
            return
        if Path(inp).resolve() == Path(out).resolve():
            messagebox.showerror("Error", "Input and output must be different files.")
            return

        from_idx = STYLE_OPTIONS.index(from_combo.get())
        to_idx = STYLE_OPTIONS.index(to_combo.get())
        if from_idx == to_idx:
            messagebox.showwarning("Same style", "Source and target styles are the same.")
            return

        api_key = _load_api_key()
        if not api_key:
            api_key = _prompt_api_key(root)
        if not api_key:
            return

        current_style = STYLE_IDS[from_idx]
        target_style = STYLE_IDS[to_idx]

        # Progress window
        prog_win = tk.Toplevel(root)
        prog_win.title("Restyling...")
        prog_win.geometry("520x220")
        prog_win.resizable(False, False)

        status_var = tk.StringVar(value="Starting...")
        ttk.Label(prog_win, textvariable=status_var, wraplength=480).pack(padx=20, pady=10)
        bar = ttk.Progressbar(prog_win, mode="indeterminate", length=480)
        bar.pack(padx=20, pady=5)
        bar.start(15)

        log_text = tk.Text(prog_win, height=6, width=65, state="disabled", font=("Consolas", 9))
        log_text.pack(padx=20, pady=5, fill="x")

        def _log(msg):
            status_var.set(msg)
            log_text.config(state="normal")
            log_text.insert("end", msg + "\n")
            log_text.see("end")
            log_text.config(state="disabled")
            prog_win.update_idletasks()

        result_holder = [None]
        error_holder = [None]

        def worker():
            try:
                result_holder[0] = restyle_docx(inp, out, current_style, target_style, api_key, _log)
            except Exception as e:
                error_holder[0] = str(e)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        def poll():
            if t.is_alive():
                prog_win.after(200, poll)
            else:
                bar.stop()
                if error_holder[0]:
                    messagebox.showerror("Failed", error_holder[0])
                    prog_win.destroy()
                elif result_holder[0]:
                    r = result_holder[0]
                    if r.get("error"):
                        messagebox.showerror("Failed", r["error"])
                    else:
                        messagebox.showinfo("Complete",
                            f"Converted {r['changed']} of {r['total']} footnotes.\n"
                            f"Skipped: {r['skipped']}  |  Errors: {r['errors']}\n\n"
                            f"Output: {r['output_path']}")
                    prog_win.destroy()

        prog_win.after(200, poll)

    ttk.Button(btn_frame, text="Restyle", command=on_restyle).pack(side="right", padx=(4, 0))
    ttk.Button(btn_frame, text="Cancel", command=root.destroy).pack(side="right")

    root.mainloop()


if __name__ == "__main__":
    main()
