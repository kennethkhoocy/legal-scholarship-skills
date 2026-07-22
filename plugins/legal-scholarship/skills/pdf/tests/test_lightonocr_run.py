"""Tests for lightonocr_run.py pure logic (no GPU, no model)."""

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import lightonocr_run
from lightonocr_run import check_vram_free_mb, parse_pages, reexec_in_venv


def test_none_spec_gives_all_pages():
    assert parse_pages(None, 3) == [0, 1, 2]


def test_range_is_one_based_inclusive():
    assert parse_pages("1-5", 10) == [0, 1, 2, 3, 4]


def test_single_page():
    assert parse_pages("3", 10) == [2]


def test_comma_list():
    assert parse_pages("1,4,7", 10) == [0, 3, 6]


def test_out_of_range_clamped():
    assert parse_pages("8-12", 10) == [7, 8, 9]
    assert parse_pages("99", 10) == []


def test_mixed_spec_with_spaces():
    assert parse_pages("1, 3-4", 10) == [0, 2, 3]


def test_duplicates_removed_order_preserved():
    assert parse_pages("1,1", 10) == [0]
    assert parse_pages("3,1-4", 10) == [2, 0, 1, 3]


def test_reversed_range_selects_nothing():
    assert parse_pages("5-3", 10) == []


def test_huge_range_clamped_before_expansion():
    # must return instantly — clamping happens before range materialization
    assert parse_pages("1-999999999", 3) == [0, 1, 2]


def test_reexec_guard_env_var_prevents_relaunch(monkeypatch):
    monkeypatch.setenv("_LIGHTONOCR_VENV", "1")
    assert reexec_in_venv() is None  # returns without SystemExit/subprocess


def test_vram_parse_ok(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout="memory.free [MiB]\n12345\n"))
    assert check_vram_free_mb() == 12345


def test_vram_parse_garbage_returns_none(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout="memory.free [MiB]\nnot-a-number\n"))
    assert check_vram_free_mb() is None


def test_main_rejects_missing_input(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", ["lightonocr_run.py", str(tmp_path / "nope.pdf"),
                                      "-o", str(tmp_path / "out.md")])
    with pytest.raises(SystemExit) as exc:
        lightonocr_run.main()
    assert exc.value.code == 2
    assert "Input not found" in capsys.readouterr().err


def test_main_rejects_output_equal_to_input(monkeypatch, tmp_path, capsys):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(sys, "argv", ["lightonocr_run.py", str(pdf), "-o", str(pdf)])
    with pytest.raises(SystemExit) as exc:
        lightonocr_run.main()
    assert exc.value.code == 2
    assert "refusing to overwrite" in capsys.readouterr().err
