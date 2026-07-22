"""Tests for scripts/anthropic_bridge.py."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest


def test_error_class_carries_install_instruction():
    from anthropic_bridge import AnthropicSkillNotInstalledError

    err = AnthropicSkillNotInstalledError()
    msg = str(err)
    assert "claude plugin marketplace add anthropics/skills" in msg
    assert "claude plugin install document-skills@anthropic-agent-skills" in msg


def test_resolver_uses_env_var(tmp_path, monkeypatch):
    from anthropic_bridge import resolve_anthropic_docx

    fake_docx = tmp_path / "docx"
    (fake_docx / "scripts").mkdir(parents=True)
    (fake_docx / "SKILL.md").write_text("# stub", encoding="utf-8")

    monkeypatch.setenv("ANTHROPIC_DOCX_PATH", str(fake_docx))
    assert resolve_anthropic_docx() == fake_docx


def test_resolver_raises_when_env_path_invalid(tmp_path, monkeypatch):
    from anthropic_bridge import AnthropicSkillNotInstalledError, resolve_anthropic_docx

    bogus = tmp_path / "nope"
    bogus.mkdir()  # exists but missing SKILL.md and scripts/
    monkeypatch.setenv("ANTHROPIC_DOCX_PATH", str(bogus))
    # Also force plugin-cache + fallback misses
    monkeypatch.setattr("anthropic_bridge._plugin_cache_candidates", lambda: [])
    monkeypatch.setattr("anthropic_bridge._fallback_candidates", lambda: [])
    with pytest.raises(AnthropicSkillNotInstalledError):
        resolve_anthropic_docx()


def test_resolver_finds_real_plugin_install():
    """When the plugin is actually installed, resolver returns its path."""
    from anthropic_bridge import resolve_anthropic_docx

    base = Path.home() / ".claude" / "plugins" / "cache" / "anthropic-agent-skills" / "document-skills"
    if not base.is_dir():
        pytest.skip("Anthropic docx plugin not installed in this environment")

    resolved = resolve_anthropic_docx()
    assert resolved.is_dir()
    assert (resolved / "SKILL.md").is_file()
    assert (resolved / "scripts").is_dir()
    assert (resolved / "scripts" / "office" / "unpack.py").is_file()


def test_anthropic_script_resolves_office_unpack():
    from anthropic_bridge import anthropic_script

    base = Path.home() / ".claude" / "plugins" / "cache" / "anthropic-agent-skills" / "document-skills"
    if not base.is_dir():
        pytest.skip("plugin not installed")

    path = anthropic_script("office/unpack.py")
    assert path.is_file()
    assert path.name == "unpack.py"


def test_run_anthropic_invokes_script(tmp_path):
    """Smoke test: unpack a fixture .docx and assert the output dir was populated."""
    from anthropic_bridge import run_anthropic

    base = Path.home() / ".claude" / "plugins" / "cache" / "anthropic-agent-skills" / "document-skills"
    if not base.is_dir():
        pytest.skip("plugin not installed")

    fixture = Path(__file__).resolve().parent / "fixtures" / "clean.docx"
    out_dir = tmp_path / "unpacked"
    result = run_anthropic("office/unpack.py", str(fixture), str(out_dir))
    assert result.returncode == 0
    assert (out_dir / "word" / "document.xml").is_file()
