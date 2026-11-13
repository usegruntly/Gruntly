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


# ---- suggesting a parent and a child from what is here
def facts(parents_=(), children=(), keys_=(), local=False):
    return {"parents": {n: n in parents_ for n in ("claude", "opencode", "qwen", "hermes", "codex", "gemini", "aider")},
            "children": {n: n in children for n in ("claude", "opencode", "qwen", "hermes", "codex", "gemini", "aider", "generic")},
            "keys": {p.name: p.name in keys_ for p in op.providers.ALL.values() if p.kind == "hosted"}, "local_up": local}


def test_claude_code_is_the_suggested_parent_when_it_is_installed_and_a_local_child_when_the_server_answers():
    s = op.suggest(facts(parents_=("claude", "opencode"), children=("opencode", "qwen"), local=True))
    assert s["parent"]["harness"] == "claude" and "measured live" in s["parent"]["reason"] and s["parent"]["provider"] is None
    assert s["child"] == {"harness": "opencode", "provider": "local", "reason": s["child"]["reason"]} and "no API dollars" in s["child"]["reason"] and s["missing"] == []


def test_without_claude_a_lean_harness_with_a_provider_it_can_use_is_suggested_and_codex_needs_a_responses_provider():
    s = op.suggest(facts(parents_=("codex",), keys_=("deepseek",)))
    assert any("codex is installed but has no provider it can use" in m for m in s["missing"])                              # deepseek does not serve the Responses API
    assert s["parent"]["harness"] == "direct" and "no installed parent harness can use a provider you have a key for" in s["parent"]["reason"]
    s = op.suggest(facts(parents_=("codex", "opencode"), keys_=("deepseek", "openrouter")))
    assert s["parent"]["harness"] == "opencode" and s["parent"]["provider"] in ("deepseek", "openrouter")
    s = op.suggest(facts(parents_=("codex",), keys_=("openai",)))
    assert (s["parent"]["harness"], s["parent"]["provider"]) == ("codex", "openai") and "has a key" in s["parent"]["reason"]
    s = op.suggest(facts(parents_=("gemini",), keys_=("openai", "gemini")))
    assert (s["parent"]["harness"], s["parent"]["provider"]) == ("gemini", "gemini")


def test_with_no_harness_but_a_key_the_direct_loop_is_suggested_and_with_nothing_the_missing_list_says_what_to_get():
    s = op.suggest(facts(keys_=("openrouter",)))
    assert (s["parent"]["harness"], s["parent"]["provider"]) == ("direct", "openrouter") and "needs no install" in s["parent"]["reason"]
    s = op.suggest(facts())
    assert s["parent"] is None and s["child"] is None and len(s["missing"]) == 2 and "gruntly auth set" in " ".join(s["missing"])


def test_the_child_falls_back_to_a_free_tier_provider_then_to_a_paid_claude_child_and_says_which():
    s = op.suggest(facts(children=("opencode",), keys_=("gemini",)))
    assert (s["child"]["harness"], s["child"]["provider"]) == ("opencode", "gemini") and "free tier" in s["child"]["reason"]
    s = op.suggest(facts(children=("claude",)))
    assert s["child"]["harness"] == "claude" and "paid" in s["child"]["reason"]
    s = op.suggest(facts(children=("gemini",), keys_=("openai",)))                                  # gemini CLI cannot use openai through a free-tier key it does not have
    assert s["child"] is None or s["child"]["harness"] != "gemini" or s["child"]["provider"] != "openai"


def test_the_suggestion_prints_without_a_key_and_apply_saves_the_parent_table_and_the_child_harness(cfg, monkeypatch, capsys):
    monkeypatch.setattr(op, "gather", lambda: facts(parents_=("claude",), children=("qwen",), local=True))
    assert cli.main(["parent", "suggest"]) == 0
    out = capsys.readouterr().out
    assert "Parent: claude (delegating)" in out and "Child:  qwen on local" in out and "--apply" in out
    assert cli.main(["parent", "suggest", "--apply"]) == 0
    assert op.read_table(cfg / ".gruntly.toml") == {"harness": "claude", "mode": "delegating"}
    import tomllib
    assert tomllib.loads((cfg / ".gruntly.toml").read_text(encoding="utf8"))["harness"] == "qwen"          # the top-level child harness, beside the [parent] table
    monkeypatch.setattr(op, "gather", lambda: facts())
    assert cli.main(["parent", "suggest", "--apply"]) == 2


def test_gather_reads_the_machine_without_returning_a_key(cfg, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-SECRET-xyz")
    monkeypatch.setattr("gruntly.doctor.probe_endpoint", lambda *a, **k: {"ok": False})
    f = op.gather()
    assert f["keys"]["groq"] is True and f["keys"]["openai"] in (True, False) and f["local_up"] is False
    assert "gsk-SECRET-xyz" not in repr(f) and "claude" in f["parents"] and "opencode" in f["children"]
