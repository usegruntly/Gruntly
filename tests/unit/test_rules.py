from gruntly import cli, rules


def test_rules_are_added_listed_and_removed(tmp_path, capsys, monkeypatch):
    p = rules.add(tmp_path, "Do not change the public API of tool/cli.py")
    assert p == tmp_path / ".gruntly" / "rules.md"
    assert rules.person_rules(tmp_path).startswith("- Do not change the public API of tool/cli.py (")
    rules.add(tmp_path, "Use pytest fixtures (2026-01-01)")
    assert rules.remove(tmp_path, "public api") and "public API" not in rules.person_rules(tmp_path)
    assert rules.remove(tmp_path, "1") == ["Use pytest fixtures (2026-01-01)"] and rules.person_rules(tmp_path) == ""


def test_session_rules_join_the_project_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc")
    rules.add(tmp_path, "Project rule (2026-01-01)")
    rules.add(tmp_path, "Today only (2026-01-01)", session=True)
    assert rules.person_rules(tmp_path) == "- Project rule (2026-01-01)\n- Today only (2026-01-01)"


def test_claude_md_and_agents_md_are_attached_with_imports_followed_once_and_capped(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("@AGENTS.md\n")
    (tmp_path / "AGENTS.md").write_text("Run ruff before committing.\n@docs/style.md\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "style.md").write_text("Four spaces.\n")
    text = rules.attached(tmp_path)
    assert text.count("Run ruff") == 1 and "Four spaces." in text
    (tmp_path / "AGENTS.md").write_text("x" * 50_000)
    assert "cut at" in rules.attached(tmp_path, limit=1000)


def test_the_read_with_list_survives_edits_and_the_cli_shows_it(tmp_path, capsys, monkeypatch):
    (tmp_path / "AGENTS.md").write_text("a\n")
    rules.add(tmp_path, "Keep the API (2026-01-01)")
    assert "## Read with these rules\n- AGENTS.md" in (tmp_path / ".gruntly" / "rules.md").read_text()
    monkeypatch.setattr(cli, "_root", lambda: tmp_path)
    assert cli.main(["rules"]) == 0
    out = capsys.readouterr().out
    assert "Keep the API" in out and "read with: AGENTS.md" in out
