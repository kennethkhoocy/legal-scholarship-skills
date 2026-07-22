"""Tests for opendataloader_convert.py — verifies probe integration only.

The original wrapper logic (subprocess spawning, log tailing, tqdm bar) is unchanged
from convert_with_progress.py and is not re-tested here; only the new probe-driven
enrichment flag logic is covered.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Add scripts dir to path so we can import the module under test
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import opendataloader_convert as olc


def test_apply_probe_enrichments_scanned_sets_force_ocr(tmp_path):
    probe = {"classification": "scanned", "formula_density": 0.0}
    probe_file = tmp_path / "probe.json"
    probe_file.write_text(json.dumps(probe))

    extra_flags = olc.derive_backend_flags(str(probe_file))

    assert "--force-ocr" in extra_flags


def test_apply_probe_enrichments_formula_dense_sets_enrich_formula(tmp_path):
    probe = {"classification": "born_digital_complex", "formula_density": 0.25}
    probe_file = tmp_path / "probe.json"
    probe_file.write_text(json.dumps(probe))

    extra_flags = olc.derive_backend_flags(str(probe_file))

    assert "--enrich-formula" in extra_flags


def test_apply_probe_enrichments_simple_pdf_adds_nothing(tmp_path):
    probe = {"classification": "born_digital_simple", "formula_density": 0.0}
    probe_file = tmp_path / "probe.json"
    probe_file.write_text(json.dumps(probe))

    extra_flags = olc.derive_backend_flags(str(probe_file))

    assert extra_flags == []


def test_apply_probe_enrichments_missing_file_returns_empty():
    extra_flags = olc.derive_backend_flags("/nonexistent/probe.json")
    assert extra_flags == []


def test_apply_probe_enrichments_malformed_json_returns_empty(tmp_path):
    probe_file = tmp_path / "probe.json"
    probe_file.write_text("not valid json {[")

    extra_flags = olc.derive_backend_flags(str(probe_file))

    assert extra_flags == []


def test_argparse_supports_keep_backend_flag():
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "opendataloader_convert.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert "--keep-backend" in result.stdout


def test_argparse_supports_restart_backend_flag():
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "opendataloader_convert.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert "--restart-backend" in result.stdout


def test_derive_backend_flags_is_the_renamed_function():
    """Sanity: the renamed function exists and is accessible."""
    assert callable(olc.derive_backend_flags)


# --- Behavioral tests that exercise actual flag routing (not shape-only) ---


class _DummyProc:
    """Stand-in for subprocess.Popen used in routing tests."""

    def __init__(self):
        self.terminated = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0


def test_start_backend_passes_flags_to_popen_when_no_existing_backend(mocker, tmp_path):
    """The backend Popen argv must end with the backend_flags list."""

    # Force the "no existing backend" path: urlopen raises.
    mocker.patch("urllib.request.urlopen", side_effect=Exception("no backend"))
    # Skip the real health-check loop.
    mocker.patch.object(olc, "wait_for_health", return_value=True)

    popen_calls: list[list[str]] = []

    def fake_popen(argv, *args, **kwargs):
        popen_calls.append(list(argv))
        return _DummyProc()

    mocker.patch("subprocess.Popen", side_effect=fake_popen)

    log_path = str(tmp_path / "backend.log")
    olc.start_backend_if_needed(log_path, backend_flags=["--force-ocr", "--enrich-formula"])

    assert len(popen_calls) == 1
    argv = popen_calls[0]
    # The wrapper must invoke the backend binary, not the converter.
    assert argv[0] == "opendataloader-pdf-hybrid"
    # Backend flags must be present, in order, at the tail of argv.
    assert argv[-2:] == ["--force-ocr", "--enrich-formula"]
    # Sanity: required port/device flags are still there.
    assert "--port" in argv and "5002" in argv
    assert "--device" in argv and "auto" in argv


def test_start_backend_skips_popen_when_existing_backend_warns_about_flags(
    mocker, tmp_path, capsys
):
    """If an existing backend is running, do not spawn a new one; warn about flags."""

    # Existing backend responds — urlopen does not raise.
    mocker.patch("urllib.request.urlopen", return_value=mocker.Mock())

    # Popen must NOT be called in this branch.
    popen_mock = mocker.patch("subprocess.Popen")

    log_path = str(tmp_path / "backend.log")
    result = olc.start_backend_if_needed(log_path, backend_flags=["--force-ocr"])

    assert result is None
    assert popen_mock.call_count == 0

    out = capsys.readouterr().out
    assert "Already running on port 5002" in out
    assert "won't pick up enrichment flags" in out
    assert "--force-ocr" in out
    # Verify the corrected wording: should mention --no-hybrid, not "--hybrid off".
    assert "--no-hybrid" in out


def test_terminate_proc_tree_tree_kills_on_windows(mocker):
    """On Windows the backend must be killed as a tree (taskkill /T) so Docling's
    multiprocessing.spawn workers are reaped, not orphaned."""
    mocker.patch("platform.system", return_value="Windows")
    run = mocker.patch("subprocess.run")
    proc = mocker.MagicMock()
    proc.poll.return_value = None
    proc.pid = 4321

    olc._terminate_proc_tree(proc)

    assert run.call_count == 1
    argv = run.call_args[0][0]
    assert argv[:3] == ["taskkill", "/F", "/T"]
    assert "4321" in argv


def test_terminate_proc_tree_noop_when_already_dead(mocker):
    run = mocker.patch("subprocess.run")
    proc = mocker.MagicMock()
    proc.poll.return_value = 0  # already exited
    olc._terminate_proc_tree(proc)
    assert run.call_count == 0


def test_restart_backend_terminates_existing_and_starts_fresh(mocker, tmp_path):
    """With restart=True and a backend already running, the wrapper must
    terminate the old one and start a fresh backend carrying the flags."""

    # A backend IS already running (urlopen succeeds).
    mocker.patch("urllib.request.urlopen", return_value=mocker.Mock())
    # Spy on the terminate helper and the port-free wait so we don't touch the OS.
    term = mocker.patch.object(olc, "_terminate_backend_on_port")
    mocker.patch.object(olc, "_wait_for_port_free", return_value=True)
    mocker.patch.object(olc, "wait_for_health", return_value=True)

    popen_calls: list[list[str]] = []

    def fake_popen(argv, *args, **kwargs):
        popen_calls.append(list(argv))
        return _DummyProc()

    mocker.patch("subprocess.Popen", side_effect=fake_popen)

    log_path = str(tmp_path / "backend.log")
    proc = olc.start_backend_if_needed(
        log_path, backend_flags=["--enrich-formula"], restart=True
    )

    # The old backend was terminated, and a new one was spawned with the flag.
    term.assert_called_once()
    assert len(popen_calls) == 1
    argv = popen_calls[0]
    assert argv[0] == "opendataloader-pdf-hybrid"
    assert "--enrich-formula" in argv
    assert proc is not None


def test_start_backend_no_flags_no_warning(mocker, tmp_path, capsys):
    """If no backend_flags are derived, no warning should appear."""

    mocker.patch("urllib.request.urlopen", return_value=mocker.Mock())
    mocker.patch("subprocess.Popen")

    log_path = str(tmp_path / "backend.log")
    olc.start_backend_if_needed(log_path, backend_flags=[])

    out = capsys.readouterr().out
    assert "Already running on port 5002" in out
    assert "won't pick up enrichment flags" not in out


def test_start_backend_tree_kills_proc_on_health_check_failure(mocker, tmp_path):
    """If wait_for_health returns False, the spawned proc must be tree-killed —
    not merely terminate()'d — so Docling's multiprocessing.spawn workers are
    reaped along with the parent before sys.exit(1). Regression guard for the
    audit finding that this failure path used a bare proc.terminate().
    """

    # Force the "no existing backend" path so we go down the Popen branch.
    mocker.patch("urllib.request.urlopen", side_effect=Exception("no backend"))
    # Health check fails.
    mocker.patch.object(olc, "wait_for_health", return_value=False)

    proc = mocker.MagicMock()
    proc.poll.return_value = None  # still running → must be reaped
    mocker.patch("subprocess.Popen", return_value=proc)
    tree_kill = mocker.patch.object(olc, "_terminate_proc_tree")

    log_path = str(tmp_path / "backend.log")
    with pytest.raises(SystemExit) as exc:
        olc.start_backend_if_needed(log_path, backend_flags=[])

    assert exc.value.code == 1
    tree_kill.assert_called_once_with(proc)


def test_terminate_proc_tree_posix_terminates_then_waits(mocker):
    """On POSIX, _terminate_proc_tree falls back to terminate()/wait() on the
    parent (the taskkill tree-kill is Windows-only)."""
    mocker.patch("platform.system", return_value="Linux")
    proc = mocker.MagicMock()
    proc.poll.return_value = None
    proc.wait.return_value = 0

    olc._terminate_proc_tree(proc)

    proc.terminate.assert_called_once()
    proc.wait.assert_called_once()
    proc.kill.assert_not_called()


def test_terminate_proc_tree_posix_kills_on_timeout(mocker):
    """If terminate() doesn't stop the proc within the wait timeout, kill()."""
    mocker.patch("platform.system", return_value="Linux")
    proc = mocker.MagicMock()
    proc.poll.return_value = None
    proc.wait.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=5)

    olc._terminate_proc_tree(proc)

    proc.terminate.assert_called_once()
    proc.kill.assert_called_once()


# --- M-2: progress total respects --pages subset ------------------------------


def test_progress_total_for_pages_none_returns_total():
    assert olc._progress_total_for_pages(None, 100) == 100


def test_progress_total_for_pages_simple_range():
    assert olc._progress_total_for_pages("1-10", 100) == 10


def test_progress_total_for_pages_single_page_range():
    assert olc._progress_total_for_pages("5-5", 100) == 1


def test_progress_total_for_pages_complex_format_falls_back_to_total():
    # Comma-separated / multi-range specs aren't parsed; bar falls back to
    # the whole-document count with an [info] note from main().
    assert olc._progress_total_for_pages("3,5,7-9", 100) == 100


def test_progress_total_for_pages_empty_string_returns_total():
    assert olc._progress_total_for_pages("", 100) == 100


def test_progress_total_for_pages_handles_whitespace():
    assert olc._progress_total_for_pages("  1-10  ", 100) == 10


def test_start_backend_default_backend_flags_is_safe():
    """Defensive check: backend_flags=None must not cause a TypeError on join.

    Guards against the classic mutable-default-arg footgun (backend_flags=[]).
    """
    import inspect

    sig = inspect.signature(olc.start_backend_if_needed)
    default = sig.parameters["backend_flags"].default
    # Either None (safe sentinel) or an empty tuple is acceptable;
    # a mutable [] default is a known Python anti-pattern.
    assert default is None or default == ()


def test_converter_command_in_main_does_not_carry_backend_flags(mocker, tmp_path):
    """Behavioral regression guard for commit 8841866.

    The previous bug was that backend enrichment flags (--force-ocr,
    --enrich-formula) derived from the probe were appended to the
    `opendataloader-pdf` (converter) argv, not the
    `opendataloader-pdf-hybrid` (backend) argv. The converter rejects
    those flags. Exercise main() end-to-end with a probe JSON that
    derives both flags, and assert the converter Popen call's argv
    contains neither.
    """
    # Probe JSON that derives both --force-ocr and --enrich-formula.
    probe_file = tmp_path / "probe.json"
    probe_file.write_text(json.dumps({"classification": "scanned", "formula_density": 0.5}))

    # A minimal real PDF so the input-path existence check passes and
    # count_pages() returns a real number.
    pdf_file = tmp_path / "doc.pdf"
    # Use the same fixture maker the rest of the test suite relies on.
    from tests.fixtures import make_simple_pdf
    make_simple_pdf(pdf_file, num_pages=1)

    # Capture every Popen call's argv.
    popen_calls: list[list[str]] = []

    def fake_popen(argv, *args, **kwargs):
        popen_calls.append(list(argv))
        # Return a dummy proc that "succeeds" instantly.
        proc = mocker.MagicMock()
        proc.poll.return_value = 0
        proc.wait.return_value = 0
        proc.returncode = 0
        proc.stderr = iter([])  # main() iterates this; empty = no progress events
        return proc

    mocker.patch("subprocess.Popen", side_effect=fake_popen)
    # Pretend an existing backend is already healthy so start_backend_if_needed
    # short-circuits — keeps the test focused on the converter call.
    mocker.patch("urllib.request.urlopen", return_value=mocker.Mock())
    # Threads in main() need a stop signal eventually; the dummy proc returns
    # immediately, so the daemon log-tailer will exit when stop_event is set.
    mocker.patch.object(olc, "tail_log_for_progress", return_value=None)

    # Invoke main() with the CLI-equivalent argv.
    test_argv = [
        "opendataloader_convert.py",
        str(pdf_file),
        "--probe-output", str(probe_file),
    ]
    mocker.patch.object(sys, "argv", test_argv)

    olc.main()

    # There should be exactly one Popen call (the converter — the backend
    # Popen branch was skipped because urlopen succeeded). If two appear,
    # something about the test setup changed; check the first converter call.
    converter_calls = [argv for argv in popen_calls if argv[0] == "opendataloader-pdf"]
    assert len(converter_calls) == 1, f"Expected one converter Popen, got {popen_calls}"
    converter_argv = converter_calls[0]

    # Core assertion: backend-only flags must NOT appear in the converter argv.
    assert "--force-ocr" not in converter_argv
    assert "--enrich-formula" not in converter_argv
    # Sanity: the converter argv should still carry the standard flags.
    assert "--hybrid" in converter_argv
    assert "docling-fast" in converter_argv
    assert str(pdf_file) in converter_argv
