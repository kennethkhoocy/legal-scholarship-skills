#!/usr/bin/env python3
"""
Tkinter GUI launcher for cite-placement.

Three pipelines:
  - Inline:    place new citations as inline \\cite / author-date refs in a .tex manuscript
  - Footnotes: place new citations from .xlsx as footnotes in a manuscript (.tex or .docx)
  - Restyle:   convert ALL existing footnote citations from one style to another

Supports both LaTeX (.tex) and Word (.docx) manuscripts for the footnote and
restyle pipelines. When the input is .docx, the pipeline uses OOXML footnote
extraction and insertion via the bundled scripts/core/docx_support/ module.
The inline pipeline is LaTeX-only (.tex in, .tex out).

Runnable standalone:  python scripts/launcher.py
Importable:           from scripts.launcher import launch
"""

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

MANUSCRIPT_FILETYPES = [
    ("Manuscripts", "*.tex *.docx"),
    ("LaTeX files", "*.tex"),
    ("Word documents", "*.docx"),
    ("All files", "*.*"),
]

STYLE_OPTIONS = [
    "Bluebook (21st ed.)",
    "OSCOLA (4th ed.)",
    "Chicago (17th ed., notes-bib)",
    "APA (7th ed.)",
    "McGill Guide (9th ed.)",
]
STYLE_IDS = ["bluebook", "oscola", "chicago", "apa", "mcgill"]

# Inline citation style → bibliographystyle id mapping
STYLE_MAP = {
    "APA": "apa",
    "MLA": "mla",
    "Harvard": "harvard",
    "Chicago (Author-Date)": "chicago_author_date",
    "Chicago (Notes)": "chicago_notes",
    "IEEE": "ieee",
    "Vancouver": "vancouver",
}


def _style_id(combo: ttk.Combobox) -> str:
    return STYLE_IDS[STYLE_OPTIONS.index(combo.get())]


def launch() -> dict | None:
    """Open the launcher GUI. Returns the config dict, or None if cancelled."""

    result: dict | None = None
    output_manually_edited = False

    # ── window ──────────────────────────────────────────────────────
    root = tk.Tk()
    root.title("cite-placement — Setup")
    root.resizable(True, False)

    outer = ttk.Frame(root, padding=10)
    outer.grid(sticky="nsew")
    root.columnconfigure(0, weight=1)
    outer.columnconfigure(0, weight=1)

    entries: dict[str, ttk.Entry] = {}

    # ═══════════════════════════════════════════════════════════════
    # FILE SELECTION (shared by all pipelines)
    # ═══════════════════════════════════════════════════════════════
    file_frame = ttk.LabelFrame(outer, text="Files (accepts .tex and .docx)", padding=8)
    file_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    file_frame.columnconfigure(1, weight=1)

    def _add_file_row(parent, row: int, label: str, key: str) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
        entry = ttk.Entry(parent, width=60)
        entry.grid(row=row, column=1, sticky="ew", pady=3)
        entries[key] = entry
        return entry

    _add_file_row(file_frame, 0, "Project Folder:", "project_folder")

    def _project_or_home() -> str:
        p = entries["project_folder"].get().strip()
        return p if p and Path(p).is_dir() else str(Path.home())

    def browse_project():
        initial = entries["project_folder"].get().strip() or str(Path.home())
        d = filedialog.askdirectory(initialdir=initial, title="Select Project Folder")
        if d:
            entries["project_folder"].delete(0, tk.END)
            entries["project_folder"].insert(0, d)

    ttk.Button(file_frame, text="Browse…", command=browse_project).grid(
        row=0, column=2, padx=(4, 0), pady=3)

    _add_file_row(file_frame, 1, "Input Manuscript:", "input_tex")

    def browse_tex():
        initial = _project_or_home()
        f = filedialog.askopenfilename(
            initialdir=initial, title="Select Input Manuscript (.tex or .docx)",
            filetypes=MANUSCRIPT_FILETYPES)
        if f:
            entries["input_tex"].delete(0, tk.END)
            entries["input_tex"].insert(0, f)
            _auto_populate_output(f)

    ttk.Button(file_frame, text="Browse…", command=browse_tex).grid(
        row=1, column=2, padx=(4, 0), pady=3)

    _add_file_row(file_frame, 2, "Input .xlsx File (placement only):", "input_xlsx")

    def browse_xlsx():
        proj = entries["project_folder"].get().strip()
        tex = entries["input_tex"].get().strip()
        if proj and Path(proj).is_dir():
            initial = proj
        elif tex and Path(tex).is_file():
            initial = str(Path(tex).parent)
        else:
            initial = str(Path.home())
        f = filedialog.askopenfilename(
            initialdir=initial, title="Select Input .xlsx File",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")])
        if f:
            entries["input_xlsx"].delete(0, tk.END)
            entries["input_xlsx"].insert(0, f)

    ttk.Button(file_frame, text="Browse…", command=browse_xlsx).grid(
        row=2, column=2, padx=(4, 0), pady=3)

    _add_file_row(file_frame, 3, "Output File:", "output_tex")

    def _on_output_edited(*_args):
        nonlocal output_manually_edited
        output_manually_edited = True

    entries["output_tex"].bind("<Key>", _on_output_edited)

    def _auto_populate_output(input_path_str: str):
        nonlocal output_manually_edited
        if output_manually_edited:
            return
        p = Path(input_path_str)
        out = p.parent / f"{p.stem}_cited{p.suffix}"
        entries["output_tex"].delete(0, tk.END)
        entries["output_tex"].insert(0, str(out))

    def browse_output():
        nonlocal output_manually_edited
        tex = entries["input_tex"].get().strip()
        initial = str(Path(tex).parent) if tex and Path(tex).parent.is_dir() else str(Path.home())
        ext = Path(tex).suffix if tex else ".tex"
        f = filedialog.asksaveasfilename(
            initialdir=initial, title="Select Output File",
            filetypes=MANUSCRIPT_FILETYPES,
            defaultextension=ext)
        if f:
            entries["output_tex"].delete(0, tk.END)
            entries["output_tex"].insert(0, f)
            output_manually_edited = True

    ttk.Button(file_frame, text="Browse…", command=browse_output).grid(
        row=3, column=2, padx=(4, 0), pady=3)

    # ── shared combo helper (used by inline + footnote + restyle frames) ──
    def _add_combo(parent, row, label, values, default, width=30):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
        combo = ttk.Combobox(parent, values=values, state="readonly", width=width)
        combo.set(default)
        combo.grid(row=row, column=1, sticky="w", pady=3)
        return combo

    # ═══════════════════════════════════════════════════════════════
    # INLINE PLACEMENT PIPELINE (.tex only)
    # ═══════════════════════════════════════════════════════════════
    inline_frame = ttk.LabelFrame(outer, text="Inline Placement (\\cite / author-date)", padding=8)
    inline_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    inline_frame.columnconfigure(1, weight=1)

    inline_style_combo = _add_combo(inline_frame, 0, "Citation Style:", list(STYLE_MAP.keys()), "Chicago (Author-Date)")
    inline_plan_combo = _add_combo(inline_frame, 1, "Placement Plan:", ["Use cached (if available)", "Force regenerate"], "Use cached (if available)")
    inline_hitl_combo = _add_combo(inline_frame, 2, "HITL Review:", ["Pause for review", "Auto-approve"], "Pause for review")
    inline_mode_combo = _add_combo(inline_frame, 3, "Citation Mode:", ["Selective", "Comprehensive"], "Selective")
    inline_insert_combo = _add_combo(inline_frame, 4, "Insertion Style:", ["Prose-integrated", "Simple"], "Prose-integrated")

    inline_verify_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        inline_frame, text="Verify existing citations (OpenAlex / CrossRef / Google Scholar)",
        variable=inline_verify_var,
    ).grid(row=5, column=0, columnspan=2, sticky="w", pady=3)

    inline_btn_frame = ttk.Frame(inline_frame)
    inline_btn_frame.grid(row=6, column=0, columnspan=3, sticky="e", pady=(6, 0))
    inline_btn = ttk.Button(inline_btn_frame, text="Run Inline Placement")
    inline_btn.pack(side="right")

    # ═══════════════════════════════════════════════════════════════
    # FOOTNOTE PLACEMENT PIPELINE
    # ═══════════════════════════════════════════════════════════════
    place_frame = ttk.LabelFrame(outer, text="Footnote Placement", padding=8)
    place_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
    place_frame.columnconfigure(1, weight=1)

    place_style_combo = _add_combo(place_frame, 0, "Citation Style:", STYLE_OPTIONS, STYLE_OPTIONS[0])
    plan_combo = _add_combo(place_frame, 1, "Placement Plan:", ["Use cached (if available)", "Force regenerate"], "Use cached (if available)")
    hitl_combo = _add_combo(place_frame, 2, "HITL Review:", ["Pause for review", "Auto-approve"], "Pause for review")
    mode_combo = _add_combo(place_frame, 3, "Citation Mode:", ["Selective", "Comprehensive"], "Selective")

    verify_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        place_frame, text="Verify existing citations (OpenAlex / CrossRef / Google Scholar)",
        variable=verify_var,
    ).grid(row=4, column=0, columnspan=2, sticky="w", pady=3)

    place_btn_frame = ttk.Frame(place_frame)
    place_btn_frame.grid(row=5, column=0, columnspan=3, sticky="e", pady=(6, 0))
    run_btn = ttk.Button(place_btn_frame, text="Run Placement")
    run_btn.pack(side="right")

    # ═══════════════════════════════════════════════════════════════
    # RESTYLE PIPELINE
    # ═══════════════════════════════════════════════════════════════
    restyle_frame = ttk.LabelFrame(outer, text="Restyle Pipeline — Convert Existing Citations (.tex / .docx)", padding=8)
    restyle_frame.grid(row=3, column=0, sticky="ew", pady=(0, 8))
    restyle_frame.columnconfigure(1, weight=1)

    current_style_combo = _add_combo(restyle_frame, 0, "Current Style:", STYLE_OPTIONS, STYLE_OPTIONS[0])
    target_style_combo = _add_combo(restyle_frame, 1, "Restyle To:", STYLE_OPTIONS, STYLE_OPTIONS[1])

    restyle_btn_frame = ttk.Frame(restyle_frame)
    restyle_btn_frame.grid(row=2, column=0, columnspan=3, sticky="e", pady=(6, 0))
    restyle_btn = ttk.Button(restyle_btn_frame, text="Run Restyle")
    restyle_btn.pack(side="right")

    # ═══════════════════════════════════════════════════════════════
    # UTILITIES
    # ═══════════════════════════════════════════════════════════════
    util_lframe = ttk.LabelFrame(outer, text="Utilities", padding=8)
    util_lframe.grid(row=4, column=0, sticky="ew", pady=(0, 8))

    def _get_input_tex() -> Path | None:
        tex = entries["input_tex"].get().strip()
        if not tex:
            messagebox.showerror("Missing input", "Input manuscript is required.")
            return None
        p = Path(tex)
        if not p.is_file():
            messagebox.showerror("File not found", f"Input file does not exist:\n{tex}")
            return None
        return p

    def on_strip():
        f = filedialog.askopenfilename(
            initialdir=_project_or_home(),
            title="Select .tex file to strip citations from",
            filetypes=[("LaTeX files", "*.tex"), ("All files", "*.*")]
        )
        if not f:
            return
        p = Path(f)
        out = p.parent / f"{p.stem}_stripped{p.suffix}"
        import importlib.util
        script_dir = Path(__file__).parent
        spec = importlib.util.spec_from_file_location("strip_citations", script_dir / "strip_citations.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        count = mod.process(str(p), str(out))
        messagebox.showinfo("Strip Complete",
                            f"Removed {count} footnotes with %CITE-PLACED marker.\n\nOutput: {out}")

    def _require_tex(p: Path) -> bool:
        if p.suffix.lower() == ".docx":
            messagebox.showerror("Not supported",
                                 "Regen utilities only work with .tex files.\n"
                                 "For .docx, use the Restyle Pipeline instead.")
            return False
        return True

    def on_regen_with_registry():
        p = _get_input_tex()
        if p is None or not _require_tex(p):
            return
        plan_dir = p.parent / "placement"
        reg_path = plan_dir / "footnote_registry.json"
        if not reg_path.is_file():
            messagebox.showerror("Registry Not Found",
                                 f"No footnote_registry.json found at:\n{reg_path}\n\n"
                                 "Use 'Regen (w/o registry)' instead, or run the full pipeline first.")
            return
        import importlib.util
        script_dir = Path(__file__).parent
        spec = importlib.util.spec_from_file_location("reorder_crossrefs", script_dir / "reorder_crossrefs.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        registry = mod.load_registry(plan_dir)
        tex = p.read_text(encoding="utf-8")
        tex_restored = mod.reverse_short_forms(tex, registry)
        p.write_text(tex_restored, encoding="utf-8")
        spec2 = importlib.util.spec_from_file_location("short_form", script_dir / "short_form.py")
        sf_mod = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(sf_mod)
        selected_style = _style_id(place_style_combo)
        sf_mod.process(str(p), str(p), str(plan_dir), selected_style, str(Path(__file__).parent.parent))
        messagebox.showinfo("Regenerate Complete",
                            f"Cross-references reordered in:\n{p}\n\nRegistry: {reg_path}")

    def on_regen_without_registry():
        p = _get_input_tex()
        if p is None or not _require_tex(p):
            return
        plan_dir = p.parent / "placement"
        import importlib.util
        script_dir = Path(__file__).parent
        spec = importlib.util.spec_from_file_location("short_form", script_dir / "short_form.py")
        sf_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sf_mod)
        selected_style = _style_id(place_style_combo)
        sf_mod.process(str(p), str(p), str(plan_dir), selected_style, str(Path(__file__).parent.parent))
        reg_path = plan_dir / "footnote_registry.json"
        messagebox.showinfo("Regenerate Complete",
                            f"Footnotes regenerated in:\n{p}\n\nRegistry created: {reg_path}")

    ttk.Button(util_lframe, text="Strip All Citations", command=on_strip).pack(side="left")
    ttk.Button(util_lframe, text="Regen (with registry)", command=on_regen_with_registry).pack(side="left", padx=(4, 0))
    ttk.Button(util_lframe, text="Regen (w/o registry)", command=on_regen_without_registry).pack(side="left", padx=(4, 0))

    # ═══════════════════════════════════════════════════════════════
    # CANCEL BUTTON
    # ═══════════════════════════════════════════════════════════════
    bottom = ttk.Frame(outer)
    bottom.grid(row=5, column=0, sticky="e", pady=(4, 0))
    ttk.Button(bottom, text="Cancel", command=lambda: root.destroy()).pack(side="right")

    # ── button commands ────────────────────────────────────────────

    def _validate_files(need_xlsx: bool = True) -> tuple[str, str, str, str | None] | None:
        tex = entries["input_tex"].get().strip()
        out = entries["output_tex"].get().strip()
        proj = entries["project_folder"].get().strip() or None
        if not tex:
            messagebox.showerror("Missing input", "Input manuscript is required.")
            return None
        if not Path(tex).is_file():
            messagebox.showerror("File not found", f"Input file does not exist:\n{tex}")
            return None
        ext = Path(tex).suffix.lower()
        if ext not in (".tex", ".docx"):
            messagebox.showerror("Unsupported format",
                                 f"Input must be .tex or .docx, got: {ext}")
            return None
        if not out:
            messagebox.showerror("Missing input", "Output file is required.")
            return None
        if not Path(out).parent.is_dir():
            messagebox.showerror("Invalid path", f"Output directory does not exist:\n{Path(out).parent}")
            return None
        if Path(tex).resolve() == Path(out).resolve():
            messagebox.showerror("Same file", "Input and Output must be different files (non-destructive).")
            return None
        out_ext = Path(out).suffix.lower()
        if ext != out_ext:
            messagebox.showerror("Format mismatch",
                                 f"Input ({ext}) and output ({out_ext}) formats must match.")
            return None
        if need_xlsx:
            xlsx = entries["input_xlsx"].get().strip()
            if not xlsx:
                messagebox.showerror("Missing input", "Input .xlsx File is required.")
                return None
            if not Path(xlsx).is_file():
                messagebox.showerror("File not found", f"Input .xlsx file does not exist:\n{xlsx}")
                return None
        else:
            xlsx = entries["input_xlsx"].get().strip() or ""
        return tex, xlsx, out, proj

    def _write_config(config: dict, out_path: str) -> Path:
        out_dir = Path(out_path).resolve().parent / "placement"
        out_dir.mkdir(parents=True, exist_ok=True)
        config_path = out_dir / "run_config.json"
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print(f"Config written to: {config_path}")
        print(json.dumps(config, indent=2))
        return config_path

    def _detect_format(path_str: str) -> str:
        return "docx" if Path(path_str).suffix.lower() == ".docx" else "tex"

    def on_run_inline():
        nonlocal result
        v = _validate_files(need_xlsx=True)
        if v is None:
            return
        tex, xlsx, out, proj = v
        # Inline mode is LaTeX-only: both input and output must be .tex
        if Path(tex).suffix.lower() != ".tex" or Path(out).suffix.lower() != ".tex":
            messagebox.showerror(
                "Inline is .tex only",
                "Inline placement requires a LaTeX manuscript.\n"
                "Both the input and output files must be .tex.\n\n"
                "For .docx, use the Footnote Placement panel instead.")
            return
        citation_style = STYLE_MAP.get(inline_style_combo.get(), "apa")
        if citation_style == "chicago_notes":
            proceed = messagebox.askyesno(
                "Chicago (Notes)",
                "Chicago (Notes) is a footnote style — use the Footnote Placement panel "
                "instead. Continue with inline anyway?")
            if not proceed:
                return
        config = {
            "pipeline": "inline",
            "input_format": "tex",
            "project_folder": str(Path(proj).resolve()) if proj else None,
            "input_tex": str(Path(tex).resolve()),
            "input_xlsx": str(Path(xlsx).resolve()),
            "output_tex": str(Path(out).resolve()),
            "citation_style": citation_style,
            "replan": inline_plan_combo.get() == "Force regenerate",
            "auto_approve": inline_hitl_combo.get() == "Auto-approve",
            "citation_mode": "comprehensive" if inline_mode_combo.get() == "Comprehensive" else "selective",
            "insertion_style": "simple" if inline_insert_combo.get() == "Simple" else "prose",
            "verify_citations": inline_verify_var.get(),
        }
        _write_config(config, out)
        result = config
        root.destroy()

    def on_run_placement():
        nonlocal result
        v = _validate_files(need_xlsx=True)
        if v is None:
            return
        tex, xlsx, out, proj = v
        fmt = _detect_format(tex)
        config = {
            "pipeline": "footnotes",
            "input_format": fmt,
            "project_folder": str(Path(proj).resolve()) if proj else None,
            "input_tex": str(Path(tex).resolve()),
            "input_xlsx": str(Path(xlsx).resolve()),
            "output_tex": str(Path(out).resolve()),
            "replan": plan_combo.get() == "Force regenerate",
            "auto_approve": hitl_combo.get() == "Auto-approve",
            "citation_style": _style_id(place_style_combo),
            "citation_mode": "comprehensive" if mode_combo.get() == "Comprehensive" else "selective",
            "verify_citations": verify_var.get(),
        }
        _write_config(config, out)
        result = config
        root.destroy()

    def on_run_restyle():
        nonlocal result
        v = _validate_files(need_xlsx=False)
        if v is None:
            return
        tex, xlsx, out, proj = v
        cur = _style_id(current_style_combo)
        tgt = _style_id(target_style_combo)
        if cur == tgt:
            messagebox.showwarning("Same Style", "Current Style and Restyle To are the same. Nothing to do.")
            return
        fmt = _detect_format(tex)
        config = {
            "pipeline": "restyle",
            "input_format": fmt,
            "project_folder": str(Path(proj).resolve()) if proj else None,
            "input_tex": str(Path(tex).resolve()),
            "input_xlsx": xlsx if xlsx else None,
            "output_tex": str(Path(out).resolve()),
            "current_style": cur,
            "target_style": tgt,
        }
        _write_config(config, out)

        result = config
        root.destroy()

    inline_btn.configure(command=on_run_inline)
    run_btn.configure(command=on_run_placement)
    restyle_btn.configure(command=on_run_restyle)

    root.mainloop()
    return result


if __name__ == "__main__":
    config = launch()
    if config is None:
        print("LAUNCHER_STATUS: cancelled")
    else:
        print(f"LAUNCHER_STATUS: success")
        print(f"LAUNCHER_CONFIG_PATH: {Path(config['output_tex']).parent / 'placement' / 'run_config.json'}")
