"""Tests for scripts/node_bridge.py."""

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest


def test_node_not_found_raises(monkeypatch):
    from node_bridge import NodeNotInstalledError, ensure_node

    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(NodeNotInstalledError) as exc:
        ensure_node()
    assert "npm install -g docx" not in str(exc.value)  # node-only error
    assert "node" in str(exc.value).lower()


def test_node_found_returns_path():
    from node_bridge import ensure_node

    if shutil.which("node") is None:
        pytest.skip("node not installed in this environment")

    node_path = ensure_node()
    assert node_path
    assert Path(node_path).exists() or node_path.endswith("node") or node_path.endswith("node.exe")


def test_ensure_docx_package_when_installed():
    from node_bridge import ensure_docx_package

    if shutil.which("node") is None:
        pytest.skip("node not installed")
    try:
        ensure_docx_package()
    except Exception as e:
        pytest.skip(f"docx npm package not installed: {e}")


def test_run_node_script_executes(tmp_path):
    from node_bridge import run_node_script

    if shutil.which("node") is None:
        pytest.skip("node not installed")

    script = tmp_path / "hello.mjs"
    script.write_text("console.log('hello from node');", encoding="utf-8")
    result = run_node_script(script)
    assert result.returncode == 0
    assert "hello from node" in result.stdout
