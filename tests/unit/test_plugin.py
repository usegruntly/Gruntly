"""The plugin ships a skill, commands and a hooks module; no MCP launcher (it pinned a stale tag of a private repo)."""
import json
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2] / "plugin"


def test_plugin_starts_no_mcp_server():
    assert not (PLUGIN / ".mcp.json").exists()
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf8"))
    assert "mcpServers" not in manifest


def test_gd_waits_as_long_as_agent_run():
    """/gd is one parent turn only if the injected command outlives the child; `still running` costs a second turn."""
    text = (PLUGIN / "commands" / "gd.md").read_text(encoding="utf8")
    assert "--max-block 540" in text


def test_every_page_that_teaches_the_parent_sends_a_failed_run_back_once_before_taking_over():
    root = Path(__file__).resolve().parents[2]
    pages = [PLUGIN / "skills" / "gruntly" / "SKILL.md", PLUGIN / "hooks" / "register.tsx", PLUGIN / "commands" / "gd.md",
             root / "src" / "gruntly" / "GUIDE.md", root / "src" / "gruntly" / "cli.py"]
    for page in pages:
        text = " ".join(page.read_text(encoding="utf8").split())
        assert "--continue" in text, page
        assert "failed or escalate: do it yourself" not in text and "`failed`/`escalate` = do it yourself" not in text, page
