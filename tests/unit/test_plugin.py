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
