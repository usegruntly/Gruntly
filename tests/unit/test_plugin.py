"""The plugin ships a skill, commands and a hooks module; no MCP launcher (it pinned a stale tag of a private repo)."""
import json
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"


def test_plugin_starts_no_mcp_server():
    assert not (PLUGIN / ".mcp.json").exists()
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf8"))
    assert "mcpServers" not in manifest


def test_gd_lets_gruntly_size_its_wait_to_what_claude_code_allows():
    """/gd is one parent turn only while the injected command stays in the foreground: Claude Code backgrounds it after its Bash
    default timeout, and the model then never sees the block (measured 2026-11-12). So gd.md names no wait and gruntly picks it."""
    text = (PLUGIN / "commands" / "gd.md").read_text(encoding="utf8")
    assert "gruntly do <<" in text and "--max-block" not in text


def test_the_wait_inside_a_slash_command_follows_the_bash_default_timeout(monkeypatch):
    from gruntly import cli
    monkeypatch.delenv("BASH_DEFAULT_TIMEOUT_MS", raising=False)
    assert cli._auto_block() == 100                       # under Claude Code's 120 s default: stays one turn
    monkeypatch.setenv("BASH_DEFAULT_TIMEOUT_MS", "120000")
    assert cli._auto_block() == 100
    monkeypatch.setenv("BASH_DEFAULT_TIMEOUT_MS", "600000")
    assert cli._auto_block() == 540                       # the person allowed long injected commands: one long call
    monkeypatch.setenv("BASH_DEFAULT_TIMEOUT_MS", "300000")
    assert cli._auto_block() == 270
    monkeypatch.setenv("BASH_DEFAULT_TIMEOUT_MS", "soon")
    assert cli._auto_block() == 100


def test_every_page_that_teaches_the_parent_sends_a_failed_run_back_once_before_taking_over():
    root = Path(__file__).resolve().parents[2]
    pages = [PLUGIN / "skills" / "gruntly" / "SKILL.md", PLUGIN / "hooks" / "register.tsx", PLUGIN / "commands" / "gd.md",
             root / "src" / "gruntly" / "GUIDE.md", root / "src" / "gruntly" / "cli.py"]
    for page in pages:
        text = " ".join(page.read_text(encoding="utf8").split())
        assert "--continue" in text, page
        assert "failed or escalate: do it yourself" not in text and "`failed`/`escalate` = do it yourself" not in text, page


def test_the_skill_teaches_the_parent_the_rule_and_the_flags_it_could_not_learn_elsewhere():
    """Website session, 2026-11-14: the big agent only knows what it is told. The 8+ turns rule was only in the manual (the description says 'call it directly',
    so the body may never be loaded), and --context was only in `gruntly guide` and --help."""
    text = (PLUGIN / "skills" / "gruntly" / "SKILL.md").read_text(encoding="utf8").replace("\r\n", "\n")
    front, body = text.split("\n---\n", 1)
    assert "~8+ turns" in front                                    # always loaded: it changes every decision to delegate
    for needle in ("--context PATH", "may read it, not change it", "replaces an existing untracked file", "ONE run", "gruntly guide"):
        assert needle in body, needle
