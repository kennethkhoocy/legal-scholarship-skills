#!/usr/bin/env python3
"""Manuscript Editing Pipeline — Tkinter GUI.

Provides file/folder browsers for each pipeline stage and runs pandoc
conversions with sanity checks.

Usage:
    python ~/.claude/skills/latex-to-word/gui.py
"""

import os
import re
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, ttk

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
REFERENCE_DOCX = os.path.join(SKILL_DIR, "scripts", "reference.docx")


class PipelineGUI:
    def __init__(self, root):
        self.root = root
        root.title("Manuscript Editing Pipeline")
        root.resizable(True, True)
        root.minsize(700, 520)

        # Find claude CLI once at startup
        self._claude_cmd = "claude"
        for candidate in [
            os.path.expanduser("~/AppData/Roaming/npm/claude.cmd"),
            os.path.expanduser("~/AppData/Roaming/npm/claude"),
            os.path.expanduser("~/.claude/local/bin/claude"),
        ]:
            if os.path.isfile(candidate):
                self._claude_cmd = candidate
                break
        self._has_edit_session = False  # True after first edit, enables --continue

        style = ttk.Style()
        style.configure("TButton", padding=4)
        style.configure("Action.TButton", padding=6)

        main = ttk.Frame(root, padding=12)
        main.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)

        row = 0

        # --- Project root folder ---
        ttk.Label(main, text="Project root:", font=("", 10, "bold")).grid(
            row=row, column=0, sticky="w", pady=(0, 2)
        )
        row += 1
        self.root_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.root_var).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=(0, 4)
        )
        ttk.Button(main, text="Browse...", command=self._browse_root).grid(
            row=row, column=2, sticky="e"
        )
        row += 1

        # --- Input .docx ---
        ttk.Label(main, text="Input .docx:", font=("", 10, "bold")).grid(
            row=row, column=0, sticky="w", pady=(10, 2)
        )
        row += 1
        self.input_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.input_var).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=(0, 4)
        )
        ttk.Button(main, text="Browse...", command=self._browse_input).grid(
            row=row, column=2, sticky="e"
        )
        row += 1

        # --- Intermediate .tex ---
        ttk.Label(main, text="Intermediate .tex:", font=("", 10, "bold")).grid(
            row=row, column=0, sticky="w", pady=(10, 2)
        )
        row += 1
        self.intermediate_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.intermediate_var).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=(0, 4)
        )
        ttk.Button(main, text="Browse...", command=self._browse_intermediate).grid(
            row=row, column=2, sticky="e"
        )
        row += 1

        # --- Edits (free-form prompt) ---
        ttk.Label(main, text="Edits:", font=("", 10, "bold")).grid(
            row=row, column=0, sticky="w", pady=(10, 2)
        )
        row += 1
        self.edits_text = tk.Text(main, height=5, wrap="word", font=("Consolas", 9))
        self.edits_text.grid(row=row, column=0, columnspan=2, sticky="ew", padx=(0, 4))
        ttk.Button(
            main, text="Apply Edits", command=self._run_apply_edits
        ).grid(row=row, column=2, sticky="ne")
        row += 1

        # --- Output folder ---
        ttk.Label(main, text="Output folder:", font=("", 10, "bold")).grid(
            row=row, column=0, sticky="w", pady=(10, 2)
        )
        row += 1
        self.output_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.output_var).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=(0, 4)
        )
        ttk.Button(main, text="Browse...", command=self._browse_output).grid(
            row=row, column=2, sticky="e"
        )
        row += 1

        # --- Action buttons ---
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=(14, 4), sticky="ew")
        btn_frame.columnconfigure((0, 1, 2), weight=1)

        ttk.Button(
            btn_frame, text="Step 1: docx \u2192 tex",
            style="Action.TButton", command=self._run_step1
        ).grid(row=0, column=0, padx=2, sticky="ew")
        ttk.Button(
            btn_frame, text="Step 3: tex \u2192 docx",
            style="Action.TButton", command=self._run_step3
        ).grid(row=0, column=1, padx=2, sticky="ew")
        ttk.Button(
            btn_frame, text="Full Pipeline",
            style="Action.TButton", command=self._run_full
        ).grid(row=0, column=2, padx=2, sticky="ew")
        row += 1

        # --- Log area ---
        ttk.Label(main, text="Log:", font=("", 10, "bold")).grid(
            row=row, column=0, sticky="w", pady=(10, 2)
        )
        row += 1
        self.log = tk.Text(main, height=14, wrap="word", font=("Consolas", 9))
        self.log.grid(row=row, column=0, columnspan=3, sticky="nsew")
        main.rowconfigure(row, weight=1)

        scrollbar = ttk.Scrollbar(main, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=row, column=3, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

    # --- Path helpers ---

    @staticmethod
    def _norm(path):
        """Normalize path separators for consistent display."""
        return os.path.normpath(path) if path else path

    # --- Browse helpers ---

    def _browse_root(self):
        path = filedialog.askdirectory(title="Select project root folder")
        if not path:
            return
        self.root_var.set(self._norm(path))
        # Auto-fill output based on root; input/intermediate just set initial dirs
        if not self.output_var.get():
            self.output_var.set(self._norm(os.path.join(path, "output")))

    def _browse_input(self):
        root_dir = self.root_var.get().strip()
        initial = None
        if root_dir:
            candidate = os.path.join(root_dir, "input")
            initial = candidate if os.path.isdir(candidate) else root_dir
        path = filedialog.askopenfilename(
            title="Select input .docx",
            initialdir=initial,
            filetypes=[("Word documents", "*.docx"), ("All files", "*.*")],
        )
        if path:
            self.input_var.set(self._norm(path))
            root = root_dir or os.path.dirname(os.path.dirname(path))
            basename = os.path.splitext(os.path.basename(path))[0]
            # Update intermediate if empty or not pointing to a .tex file
            current_inter = self.intermediate_var.get().strip()
            if not current_inter or not current_inter.endswith(".tex"):
                inter_dir = os.path.join(root, "intermediate")
                self.intermediate_var.set(
                    self._norm(os.path.join(inter_dir, f"{basename}_intermediate.tex"))
                )
            if not self.output_var.get():
                self.output_var.set(self._norm(os.path.join(root, "output")))

    def _browse_intermediate(self):
        # Suggest a default filename based on the input .docx
        input_path = self.input_var.get().strip()
        root_dir = self.root_var.get().strip()
        if input_path:
            basename = os.path.splitext(os.path.basename(input_path))[0]
            default_name = f"{basename}_intermediate.tex"
        else:
            default_name = "intermediate.tex"
        initial = os.path.join(root_dir, "intermediate") if root_dir else None

        path = filedialog.asksaveasfilename(
            title="Select or create intermediate .tex",
            defaultextension=".tex",
            initialfile=default_name,
            initialdir=initial,
            filetypes=[("LaTeX files", "*.tex"), ("All files", "*.*")],
            confirmoverwrite=False,
        )
        if not path:
            return

        self.intermediate_var.set(self._norm(path))
        # Auto-fill output if empty
        if not self.output_var.get():
            parent = os.path.dirname(path)
            self.output_var.set(self._norm(os.path.join(parent, "output")))

    def _browse_output(self):
        root_dir = self.root_var.get().strip()
        initial = os.path.join(root_dir, "output") if root_dir else None
        path = filedialog.askdirectory(title="Select output folder", initialdir=initial)
        if path:
            self.output_var.set(self._norm(path))

    # --- Logging ---

    def _log(self, msg):
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.root.update_idletasks()

    def _clear_log(self):
        self.log.delete("1.0", "end")

    # --- Pipeline steps ---

    def _run_in_thread(self, fn):
        """Run a pipeline function in a background thread to keep GUI responsive."""
        def wrapper():
            try:
                fn()
            except Exception as e:
                self.root.after(0, self._log, f"ERROR: {e}")
        threading.Thread(target=wrapper, daemon=True).start()

    def _run_step1(self):
        self._run_in_thread(self._step1)

    def _run_apply_edits(self):
        self._run_in_thread(self._apply_edits)

    def _run_step3(self):
        self._run_in_thread(self._step3)

    def _run_full(self):
        self._run_in_thread(self._full_pipeline)

    def _apply_edits(self):
        """Use Claude Code CLI to edit the .tex file."""
        self._clear_log()
        intermediate_path = self.intermediate_var.get().strip()
        prompt = self.edits_text.get("1.0", "end").strip()

        if not intermediate_path:
            self._log("ERROR: No intermediate .tex path specified.")
            return
        if not os.path.isfile(intermediate_path):
            self._log(f"ERROR: File not found: {intermediate_path}")
            return
        if not prompt:
            self._log("ERROR: No edit instructions provided.")
            return

        # Capture footnote count before
        with open(intermediate_path, encoding="utf-8") as f:
            orig_text = f.read()
        orig_fn = len(re.findall(r"\\footnote\{", orig_text))
        orig_lines = len(orig_text.splitlines())

        self._log(f"File: {intermediate_path}")
        self._log(f"Before: {orig_lines:,} lines, {orig_fn} footnotes")
        self._log(f"Prompt: {prompt[:200]}{'...' if len(prompt) > 200 else ''}")
        self._log("\nRunning Claude Code...")

        try:
            # Write prompt to temp file to avoid shell quoting issues
            import tempfile
            prompt_file = os.path.join(tempfile.gettempdir(), "manuscript_edit_prompt.txt")
            abs_path = os.path.abspath(intermediate_path)

            if self._has_edit_session:
                # Subsequent edit — use --continue, shorter prompt since Claude knows the file
                full_prompt = (
                    f"Apply these edits to the same file ({abs_path}):\n{prompt}\n\n"
                    f"Use the Edit tool. Do NOT write to any other path."
                )
            else:
                # First edit — full instructions
                full_prompt = (
                    f"TASK: Edit a LaTeX file IN PLACE.\n\n"
                    f"1. Read the file: {abs_path}\n"
                    f"2. Apply these edits: {prompt}\n"
                    f"3. Use the Edit tool to modify the file at: {abs_path}\n"
                    f"4. Do NOT write to any other path. Only edit: {abs_path}\n\n"
                    f"IMPORTANT: Preserve all \\footnote{{}} commands and LaTeX structure."
                )

            with open(prompt_file, "w", encoding="utf-8") as pf:
                pf.write(full_prompt)

            # Run claude in the directory of the target file
            work_dir = os.path.dirname(abs_path)

            cmd = [self._claude_cmd, "--dangerously-skip-permissions",
                   "--no-session-persistence", "-p",
                   f"Read {prompt_file} and follow its instructions exactly.",
                   "--allowedTools", "Read,Edit,Write"]
            if self._has_edit_session:
                cmd.insert(3, "--continue")

            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=300,
                cwd=work_dir,
                shell=(self._claude_cmd.endswith(".cmd")),
            )
            if result.returncode != 0:
                self._log(f"FAILED (exit {result.returncode}):\n{result.stderr}")
                return

            self._has_edit_session = True  # Enable --continue for subsequent edits
            self._log(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)

            # Check footnote count after
            with open(intermediate_path, encoding="utf-8") as f:
                new_text = f.read()
            new_fn = len(re.findall(r"\\footnote\{", new_text))
            new_lines = len(new_text.splitlines())

            self._log(f"\nAfter: {new_lines:,} lines, {new_fn} footnotes")
            if orig_fn != new_fn:
                self._log(f"WARNING: Footnote count changed ({orig_fn} -> {new_fn})")
            else:
                self._log("Footnote counts match.")

            # Compile with XeLaTeX
            self._compile_xelatex(intermediate_path)

        except FileNotFoundError:
            self._log("ERROR: 'claude' CLI not found. Ensure Claude Code is installed and on PATH.")
        except subprocess.TimeoutExpired:
            self._log("ERROR: Claude Code timed out after 5 minutes.")
        except Exception as e:
            self._log(f"ERROR: {e}")

    def _step1(self):
        """docx -> tex"""
        self._clear_log()
        input_path = self.input_var.get().strip()
        intermediate_path = self.intermediate_var.get().strip()

        if not input_path:
            self._log("ERROR: No input .docx selected.")
            return
        if not os.path.isfile(input_path):
            self._log(f"ERROR: Input file not found: {input_path}")
            return

        # If intermediate is a directory or doesn't end in .tex, derive filename
        if not intermediate_path.endswith(".tex"):
            basename = os.path.splitext(os.path.basename(input_path))[0]
            if intermediate_path and os.path.isdir(intermediate_path.rstrip(os.sep + "/")):
                inter_dir = intermediate_path.rstrip(os.sep + "/")
            else:
                root = self.root_var.get().strip() or os.path.dirname(os.path.dirname(input_path))
                inter_dir = os.path.join(root, "intermediate")
            intermediate_path = os.path.join(inter_dir, f"{basename}_intermediate.tex")
            self.intermediate_var.set(self._norm(intermediate_path))

        if not intermediate_path:
            self._log("ERROR: No intermediate .tex path specified.")
            return

        inter_dir = os.path.dirname(intermediate_path)
        os.makedirs(inter_dir, exist_ok=True)
        media_dir = os.path.join(inter_dir, "media")

        cmd = [
            "pandoc", input_path,
            "-t", "latex",
            "--standalone",
            "--pdf-engine=xelatex",
            "--wrap=auto",
            "--columns=80",
            f"--extract-media={media_dir}",
            "-o", intermediate_path,
        ]
        self._log(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self._log(f"FAILED:\n{result.stderr}")
            return
        self._log(f"Created: {intermediate_path}")

        # Sanity check
        self._sanity_check_tex(intermediate_path)

        # Compile with XeLaTeX
        self._compile_xelatex(intermediate_path)

    def _step3(self):
        """tex -> docx"""
        self._clear_log()
        intermediate_path = self.intermediate_var.get().strip()
        output_dir = self.output_var.get().strip()

        if not intermediate_path:
            self._log("ERROR: No intermediate .tex selected.")
            return
        if not os.path.isfile(intermediate_path):
            self._log(f"ERROR: Intermediate file not found: {intermediate_path}")
            return
        if not output_dir:
            self._log("ERROR: No output folder selected.")
            return

        os.makedirs(output_dir, exist_ok=True)

        # Derive output filename from intermediate filename
        basename = os.path.splitext(os.path.basename(intermediate_path))[0]
        # Replace 'intermediate_' prefix with 'output_' if present
        if basename.startswith("intermediate_"):
            out_name = "output_" + basename[len("intermediate_"):]
        else:
            out_name = "output_" + basename
        output_path = os.path.join(output_dir, out_name + ".docx")

        cmd = [
            "pandoc", intermediate_path,
            "-f", "latex",
            "-o", output_path,
        ]
        if os.path.isfile(REFERENCE_DOCX):
            cmd += [f"--reference-doc={REFERENCE_DOCX}"]
            self._log(f"Using reference doc: {REFERENCE_DOCX}")
        else:
            # Pandoc defaults give Footnote Text no size — footnotes would
            # render at full body size. Abort instead of delivering that.
            self._log(f"ERROR: {REFERENCE_DOCX} not found — aborting. "
                      f"Regenerate it with: python {os.path.join(SKILL_DIR, 'scripts', 'gen_reference.py')}")
            return

        self._log(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self._log(f"FAILED:\n{result.stderr}")
            return
        self._log(f"Created: {output_path}")

        # Round-trip sanity check
        self._sanity_check_roundtrip(intermediate_path, output_path)

    def _full_pipeline(self):
        """Step 1 then Step 3."""
        self._step1()
        if "FAILED" in self.log.get("1.0", "end") or "ERROR" in self.log.get("1.0", "end"):
            self._log("\nPipeline stopped due to errors in Step 1.")
            return
        self._log("\n--- Step 2: Edit the .tex in Claude Code or a text editor ---\n")
        self._log("Proceeding to Step 3 with current intermediate file...\n")
        self._step3()

    # --- XeLaTeX compilation ---

    def _compile_xelatex(self, tex_path, max_fix_attempts=3):
        """Compile a .tex file with XeLaTeX. If errors occur, use Claude Code to fix them."""
        abs_path = os.path.abspath(tex_path)
        tex_dir = os.path.dirname(abs_path)

        for attempt in range(1, max_fix_attempts + 1):
            self._log(f"\nCompiling with XeLaTeX (attempt {attempt})...")
            cmd = [
                "xelatex",
                "-interaction=nonstopmode",
                "-output-directory", tex_dir,
                abs_path,
            ]
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=120,
                    cwd=tex_dir,
                )
            except FileNotFoundError:
                self._log("ERROR: xelatex not found. Install TeX Live or MiKTeX.")
                return
            except subprocess.TimeoutExpired:
                self._log("ERROR: XeLaTeX timed out after 2 minutes.")
                return

            stdout = result.stdout or ""
            stderr = result.stderr or ""

            # Extract errors from the log
            errors = [l for l in stdout.splitlines()
                      if l.startswith("!") or "Fatal error" in l or "Emergency stop" in l]

            pdf_path = os.path.splitext(abs_path)[0] + ".pdf"
            if os.path.isfile(pdf_path) and not errors:
                self._log(f"PDF created: {pdf_path}")
                return  # Success

            if not errors:
                # PDF exists but there were warnings — still OK
                if os.path.isfile(pdf_path):
                    self._log(f"PDF created (with warnings): {pdf_path}")
                    return
                # No errors extracted but no PDF — show tail of log
                lines = stdout.splitlines()
                tail = "\n".join(lines[-15:]) if len(lines) > 15 else stdout
                self._log(f"XeLaTeX finished but no PDF produced:\n{tail}")
                return

            # Errors found — send to Claude Code for fixing
            error_text = "\n".join(errors[:20])  # Cap at 20 error lines
            self._log(f"XeLaTeX errors found:\n{error_text}")

            if attempt >= max_fix_attempts:
                self._log(f"\nMax fix attempts ({max_fix_attempts}) reached. Manual review needed.")
                return

            self._log(f"\nSending errors to Claude Code for fixing...")
            try:
                import tempfile
                fix_prompt_file = os.path.join(tempfile.gettempdir(), "xelatex_fix_prompt.txt")
                fix_prompt = (
                    f"The LaTeX file at {abs_path} has compilation errors.\n"
                    f"Fix ONLY the LaTeX errors below. Do not change content or meaning.\n"
                    f"Use the Edit tool to fix the file at: {abs_path}\n\n"
                    f"XELATEX ERRORS:\n{error_text}"
                )
                with open(fix_prompt_file, "w", encoding="utf-8") as pf:
                    pf.write(fix_prompt)

                fix_cmd = [self._claude_cmd, "--dangerously-skip-permissions",
                           "--no-session-persistence", "-p",
                           f"Read {fix_prompt_file} and follow its instructions exactly.",
                           "--allowedTools", "Read,Edit,Write"]
                if self._has_edit_session:
                    fix_cmd.insert(2, "--continue")

                fix_result = subprocess.run(
                    fix_cmd,
                    capture_output=True, text=True, timeout=300,
                    cwd=tex_dir,
                    shell=(self._claude_cmd.endswith(".cmd")),
                )
                self._has_edit_session = True

                if fix_result.returncode != 0:
                    self._log(f"Claude Code fix failed:\n{fix_result.stderr}")
                    return

                self._log(fix_result.stdout[-1000:] if len(fix_result.stdout) > 1000 else fix_result.stdout)
            except Exception as e:
                self._log(f"ERROR during fix attempt: {e}")
                return

    # --- Sanity checks ---

    def _sanity_check_tex(self, tex_path):
        with open(tex_path, encoding="utf-8") as f:
            text = f.read()
        lines = text.splitlines()
        footnotes = re.findall(r"\\footnote\{", text)
        bracket_citations = re.findall(r"\{\[\}\d", text)
        previews = re.findall(r"\\footnote\{([^}]{0,80})", text)[:3]

        self._log(f"\n=== Conversion Summary ===")
        self._log(f"Lines:               {len(lines):,}")
        self._log(f"\\footnote{{}} count:   {len(footnotes)}")
        self._log(f"{{[}}N: ...{{]}} count:  {len(bracket_citations)}")
        if previews:
            self._log("First 3 footnotes:")
            for p in previews:
                suffix = "..." if len(p) == 80 else ""
                self._log(f"  \\footnote{{{p}{suffix}}}")
        if len(footnotes) == 0 and len(bracket_citations) > 0:
            self._log(
                "\nNote: Bracket citations detected — run convert_bracket_footnotes.py"
            )
        elif len(footnotes) == 0 and len(bracket_citations) == 0:
            self._log("\nWARNING: No footnotes found — check the original .docx")

    def _sanity_check_roundtrip(self, tex_path, docx_path):
        with open(tex_path, encoding="utf-8") as f:
            orig_text = f.read()
        orig_fn = len(re.findall(r"\\footnote\{", orig_text))
        orig_lines = len(orig_text.splitlines())

        tmp = os.path.join(tempfile.gettempdir(), "roundtrip_check.tex")
        subprocess.run(
            ["pandoc", docx_path, "-t", "latex", "-o", tmp],
            capture_output=True, text=True,
        )
        if os.path.isfile(tmp):
            with open(tmp, encoding="utf-8") as f:
                rt_text = f.read()
            rt_fn = len(re.findall(r"\\footnote\{", rt_text))
            rt_lines = len(rt_text.splitlines())

            self._log(f"\n=== Round-trip Summary ===")
            self._log(f"Original .tex  — Lines: {orig_lines:,}  Footnotes: {orig_fn}")
            self._log(f"Round-trip .tex — Lines: {rt_lines:,}  Footnotes: {rt_fn}")
            if orig_fn != rt_fn:
                self._log(
                    f"WARNING: Footnote count mismatch ({orig_fn} vs {rt_fn})"
                )
            else:
                self._log("Footnote counts match.")
        else:
            self._log("Could not perform round-trip check.")


def main():
    root = tk.Tk()
    PipelineGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
