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


def test_every_page_that_teaches_the_parent_directs_the_child_in_words_and_does_not_take_the_job_over():
    root = Path(__file__).resolve().parents[2]
    pages = [PLUGIN / "skills" / "gruntly" / "SKILL.md", PLUGIN / "hooks" / "register.tsx", PLUGIN / "commands" / "gd.md",
             root / "src" / "gruntly" / "GUIDE.md", root / "src" / "gruntly" / "cli.py"]
    for page in pages:
        text = " ".join(page.read_text(encoding="utf8").split())
        assert "--continue" in text, page
        assert "if that fails too" not in text and "if that fails too, do it yourself" not in text, page
        assert "teacher" in text and "never the code" in text, page


def test_the_skill_teaches_the_parent_the_rule_and_the_flags_it_could_not_learn_elsewhere():
    """Website session, 2026-11-14: the big agent only knows what it is told. The 8+ turns rule was only in the manual (the description says 'call it directly',
    so the body may never be loaded), and --context was only in `gruntly guide` and --help."""
    text = (PLUGIN / "skills" / "gruntly" / "SKILL.md").read_text(encoding="utf8").replace("\r\n", "\n")
    front, body = text.split("\n---\n", 1)
    assert "~8+ turns" in front                                    # always loaded: it changes every decision to delegate
    for needle in ("--context PATH", "may read it, not change it", "hard-coded", "ONE run", "gruntly guide"):
        assert needle in body, needle


def test_mode_on_makes_the_big_agent_a_director_in_every_place_that_teaches_it():
    """Website session, 2026-11-14: it unpacked an 800 KB page with its own scripts because its instructions said never to delegate reading. In
    mode on the big agent asks the child (agent-run --ask) and works from a short answer; its own context is what every later turn re-reads."""
    root = Path(__file__).resolve().parents[2]
    for page in (PLUGIN / "skills" / "gruntly" / "SKILL.md", PLUGIN / "hooks" / "register.tsx"):
        text = " ".join(page.read_text(encoding="utf8").split())
        assert "director" in text.lower() and "--ask" in text and "screenshots" in text, page
        assert "files read first yourself" not in text, page          # the old line that sent reading back to the big agent
    guide = (root / "src" / "gruntly" / "GUIDE.md").read_text(encoding="utf8")
    assert "## Director mode" in guide and "Ingest:" in guide and "Look:" in guide
    assert "Director mode" in (root / "docs" / "mode.md").read_text(encoding="utf8")


def test_the_skill_does_not_pull_against_mode_on_and_has_no_holdout():
    """Website session, 2026-11-14: the project was in mode ON but the skill said a one-line edit is cheaper by hand, so the big agent skipped gruntly twice."""
    text = (PLUGIN / "skills" / "gruntly" / "SKILL.md").read_text(encoding="utf8").replace("\r\n", "\n")
    front, body = text.split("\n---\n", 1)
    assert "in mode on, every eligible change" in front and "in auto mode a one-line edit" in body
    assert "delegate every eligible change, small ones too" in body
    assert "holdout" not in text.lower() and "the teacher, not the doer" in body and "Do not write the code yourself" in body
    assert "outside the project works too" in body
