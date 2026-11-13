"""Choosing the parent: the `[parent]` table is edited in place, a choice that cannot work is refused with the reason, and the interactive step saves what was picked."""
import pytest

from gruntly import cli, keys, onboard, onboard_parent as op, parents


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("GRUNTLY_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "cfg").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(onboard, "project_config", lambda: tmp_path / ".gruntly.toml")
    return tmp_path


def test_the_parent_table_is_added_changed_and_cleared_without_touching_anything_else(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('# mine\nharness = "opencode"\n\n[gates]\nmax_lines = 5\n', encoding="utf8")
    op.set_table_values(p, "parent", {"harness": "codex", "mode": "delegating", "provider": None})
    text = p.read_text(encoding="utf8")
    assert text.startswith('# mine\nharness = "opencode"') and "[gates]\nmax_lines = 5" in text and '[parent]\nharness = "codex"\nmode = "delegating"' in text
    op.set_table_values(p, "parent", {"harness": "qwen", "provider": "openrouter"})
    assert op.read_table(p) == {"harness": "qwen", "mode": "delegating", "provider": "openrouter"}
    op.set_table_values(p, "parent", {"mode": None, "provider": None, "harness": None})
    assert op.read_table(p) == {} and "[gates]" in p.read_text(encoding="utf8")


def test_a_subtable_is_never_mistaken_for_the_parent_table(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[parent.generic]\ncommand = ["x"]\n', encoding="utf8")
    op.set_table_values(p, "parent", {"harness": "generic"})
    assert op.read_table(p) == {"harness": "generic", "generic": {"command": ["x"]}}


def test_a_choice_that_cannot_work_is_refused_with_the_reason(cfg):
    for args, why in ((("nope",), "unknown parent harness 'nope'"), (("aider", "delegating"), "aider cannot run in delegating mode"),
                      (("codex", None, "deepseek"), "codex cannot use deepseek: it speaks the responses API"),
                      (("gemini", None, "openai"), "gemini cannot use openai"), (("claude", None, "openai"), "only works through your own login"),
                      (("opencode", None, "nowhere"), "unknown provider 'nowhere'")):
        with pytest.raises(ValueError, match=why):
            op.validate(*args)
    op.validate("codex", "delegating", "openai")
    op.validate("opencode", "working", "ollama")


def test_save_writes_the_table_where_agent_reads_it_and_a_later_launch_resolves_it(cfg):
    path = op.save("codex", "delegating", "openai", "gpt-x", "project")
    assert path == cfg / ".gruntly.toml"
    assert parents.resolve(root=cfg) == {"parent": "codex", "model": "gpt-x", "provider": "openai", "mode": "delegating"}
    g = op.save("opencode", None, None, None, "global")
    assert g == cfg / "cfg" / "config.toml" and op.read_table(g) == {"harness": "opencode"}


def test_the_command_shows_sets_and_clears(cfg, capsys):
    assert cli.main(["parent"]) == 0
    out = capsys.readouterr().out
    assert "Parent: harness =" in out and "HARNESS" in out and "gruntly parent set" in out
    assert cli.main(["parent", "set", "codex", "--mode", "delegating", "--provider", "openai", "--model", "m"]) == 0
    assert "Saved to" in capsys.readouterr().out and op.read_table(cfg / ".gruntly.toml")["harness"] == "codex"
    assert cli.main(["parent", "set", "aider", "--mode", "delegating"]) == 2
    assert "not saved: aider cannot run in delegating mode" in capsys.readouterr().err
    assert cli.main(["parent", "set"]) == 2 and cli.main(["parent", "clear"]) == 0 and op.read_table(cfg / ".gruntly.toml") == {}


def test_the_interactive_step_saves_what_was_picked_and_can_be_skipped(cfg, monkeypatch, capsys):
    answers = iter(["y", "codex", "d", "openai", "p"])                         # set it up, codex, delegating, openai, this project
    monkeypatch.setattr(onboard, "ask", lambda prompt, default="": next(answers) or default)
    monkeypatch.setattr(onboard, "ensure_key", lambda name: True)
    monkeypatch.setattr(onboard, "choose_model", lambda name, endpoint, current=None: "gpt-x")
    op.step()
    assert op.read_table(cfg / ".gruntly.toml") == {"harness": "codex", "mode": "delegating", "provider": "openai", "model": "gpt-x"}
    assert "Saved to" in capsys.readouterr().out
    monkeypatch.setattr(onboard, "ask", lambda prompt, default="": default)
    op.step()
    assert "Skipped." in capsys.readouterr().out and op.read_table(cfg / ".gruntly.toml")["harness"] == "codex"
