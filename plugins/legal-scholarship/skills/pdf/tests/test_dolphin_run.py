"""Tests for dolphin_run.py wrapper.

dolphin_run.py orchestrates calls to demo_page.py / demo_element.py / demo_layout.py
in the user's Dolphin install (default ~/Dolphin, override DOLPHIN_DIR). These tests mock subprocess
calls — they don't actually invoke the Dolphin model.
"""

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import dolphin_run


def test_build_command_page_mode():
    cmd = dolphin_run.build_command(
        mode="page",
        input_path="/tmp/in.pdf",
        save_dir="/tmp/out",
        max_batch_size=4,
        element_type=None,
        dolphin_dir="/fake/dolphin",
    )
    assert cmd[0].endswith("python") or "python" in cmd[0].lower()
    assert "demo_page.py" in " ".join(cmd)
    assert "--input_path" in cmd
    assert "/tmp/in.pdf" in cmd
    assert "--save_dir" in cmd
    assert "/tmp/out" in cmd
    assert "--max_batch_size" in cmd
    assert "4" in cmd


def test_build_command_element_mode_requires_element_type():
    with pytest.raises(ValueError):
        dolphin_run.build_command(
            mode="element",
            input_path="/tmp/in.png",
            save_dir="/tmp/out",
            max_batch_size=4,
            element_type=None,
            dolphin_dir="/fake/dolphin",
        )


def test_build_command_element_mode_with_element_type():
    cmd = dolphin_run.build_command(
        mode="element",
        input_path="/tmp/in.png",
        save_dir="/tmp/out",
        max_batch_size=4,
        element_type="table",
        dolphin_dir="/fake/dolphin",
    )
    assert "demo_element.py" in " ".join(cmd)
    assert "--element_type" in cmd
    assert "table" in cmd


def test_build_command_layout_mode():
    cmd = dolphin_run.build_command(
        mode="layout",
        input_path="/tmp/in.pdf",
        save_dir="/tmp/out",
        max_batch_size=4,
        element_type=None,
        dolphin_dir="/fake/dolphin",
    )
    assert "demo_layout.py" in " ".join(cmd)


def test_build_command_invalid_mode_raises():
    with pytest.raises(ValueError):
        dolphin_run.build_command(
            mode="bogus",
            input_path="/tmp/in.pdf",
            save_dir="/tmp/out",
            max_batch_size=4,
            element_type=None,
            dolphin_dir="/fake/dolphin",
        )


def test_dolphin_is_installed_false_when_missing(tmp_path):
    # Optional backend: a dir without the demo script must read as not installed.
    assert dolphin_run.dolphin_is_installed(str(tmp_path), "page") is False


def test_dolphin_is_installed_true_when_script_present(tmp_path):
    (tmp_path / "demo_page.py").write_text("# stub")
    assert dolphin_run.dolphin_is_installed(str(tmp_path), "page") is True


def test_check_vram_returns_free_mb(mocker):
    fake_csv = "memory.free [MiB]\n12345\n"
    mocker.patch(
        "subprocess.run",
        return_value=type("R", (), {"stdout": fake_csv, "returncode": 0})(),
    )
    free_mb = dolphin_run.check_vram_free_mb()
    assert free_mb == 12345


def test_check_vram_handles_nvidia_smi_failure(mocker):
    mocker.patch(
        "subprocess.run",
        return_value=type("R", (), {"stdout": "", "returncode": 1, "stderr": "no driver"})(),
    )
    free_mb = dolphin_run.check_vram_free_mb()
    assert free_mb is None


def test_verify_vram_released_finds_marker():
    output = "Processing page 12...\nVRAM released: 80 MB remaining\nDone."
    assert dolphin_run.verify_vram_released(output) is True


def test_verify_vram_released_missing_marker():
    output = "Processing page 12...\nDone."
    assert dolphin_run.verify_vram_released(output) is False


def test_build_command_element_mode_omits_max_batch_size():
    cmd = dolphin_run.build_command(
        mode="element",
        input_path="/tmp/in.png",
        save_dir="/tmp/out",
        max_batch_size=4,
        element_type="table",
        dolphin_dir="/fake/dolphin",
    )
    assert "--max_batch_size" not in cmd


def test_build_command_layout_mode_omits_max_batch_size():
    cmd = dolphin_run.build_command(
        mode="layout",
        input_path="/tmp/in.pdf",
        save_dir="/tmp/out",
        max_batch_size=4,
        element_type=None,
        dolphin_dir="/fake/dolphin",
    )
    assert "--max_batch_size" not in cmd


# --- --print_results gating ---


def test_build_command_element_mode_with_print_results():
    cmd = dolphin_run.build_command(
        mode="element",
        input_path="/tmp/in.png",
        save_dir="/tmp/out",
        max_batch_size=4,
        element_type="table",
        dolphin_dir="/fake/dolphin",
        print_results=True,
    )
    assert "--print_results" in cmd


def test_build_command_element_mode_without_print_results_omits_it():
    cmd = dolphin_run.build_command(
        mode="element",
        input_path="/tmp/in.png",
        save_dir="/tmp/out",
        max_batch_size=4,
        element_type="table",
        dolphin_dir="/fake/dolphin",
        print_results=False,
    )
    assert "--print_results" not in cmd


def test_build_command_page_mode_print_results_raises():
    # demo_page.py does not accept --print_results; the wrapper must refuse.
    with pytest.raises(ValueError, match="print_results"):
        dolphin_run.build_command(
            mode="page",
            input_path="/tmp/in.pdf",
            save_dir="/tmp/out",
            max_batch_size=4,
            element_type=None,
            dolphin_dir="/fake/dolphin",
            print_results=True,
        )


def test_build_command_layout_mode_print_results_raises():
    # demo_layout.py does not accept --print_results; the wrapper must refuse.
    with pytest.raises(ValueError, match="print_results"):
        dolphin_run.build_command(
            mode="layout",
            input_path="/tmp/in.pdf",
            save_dir="/tmp/out",
            max_batch_size=4,
            element_type=None,
            dolphin_dir="/fake/dolphin",
            print_results=True,
        )


def test_cli_exposes_print_results_flag():
    """Smoke test: the CLI surface advertises --print_results in --help."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "dolphin_run.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert "--print_results" in result.stdout
