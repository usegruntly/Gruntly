"""`gruntly agent --parent --mode --model --provider`: settings, flags, the working mode, the fallback, with a fake parent harness."""
import sys

import pytest

from gruntly import cli, parents
from gruntly.adapters.base import Detection
from gruntly.parents import base
from gruntly.spec import build_spec


class FakeParent:
    """A parent whose harness is a python one-liner. Delegating prints `reply`, or its model and provider; working echoes the task it got."""
    name = "fakep"
    reply = None

    def detect(self):
        return Detection(True, "fake 1")

    def command(self, task, mode, model=None, provider=None, structured=False):
        if mode == "working":
            code = "import sys; print('WORKED:' + sys.stdin.read())"
        elif FakeParent.reply is not None:
            code = f"print({FakeParent.reply!r})"
        else:
            code = "import os, sys; print('DELEGATED:' + os.environ['M'] + ',' + os.environ['P'] + ':' + sys.stdin.read())"
        return base.ParentCommand([sys.executable, "-c", code], {"M": str(model), "P": str(provider)}, task, {}, ["fake limit"])

    def parse(self, stdout, stderr, exit_code):
        return base.ParentOutcome(stdout.strip(), exit_code != 0)

    def capabilities(self):
        return base.ParentCaps()

    def cancel(self, proc):
        pass


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("GRUNTLY_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "cfg").mkdir()
    monkeypatch.setattr(parents, "table", lambda: {"fakep": FakeParent, "other": FakeParent})
    monkeypatch.setattr(parents, "pick_installed", lambda mode="delegating": "fakep")
    FakeParent.reply = None
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_settings_come_from_the_global_file_then_the_project_file_and_ignore_unknown_keys(cfg):
    (cfg / "cfg" / "config.toml").write_text('[parent]\nharness = "other"\nmodel = "m-global"\nmode = "working"\nsurprise = 1\n')
    proj = cfg / "proj"
    proj.mkdir()
    (proj / ".gruntly.toml").write_text('[parent]\nmodel = "m-project"\nprovider = "openrouter"\n')
    assert parents.settings() == {"harness": "other", "model": "m-global", "mode": "working"}
    assert parents.settings(proj) == {"harness": "other", "model": "m-project", "mode": "working", "provider": "openrouter"}


def test_a_flag_beats_the_settings_and_the_defaults_are_the_installed_harness_in_delegating_mode(cfg):
    assert parents.resolve() == {"parent": "fakep", "model": None, "provider": None, "mode": "delegating"}
    (cfg / "cfg" / "config.toml").write_text('[parent]\nharness = "other"\nmodel = "m1"\n')
    assert parents.resolve()["parent"] == "other" and parents.resolve(parent="fakep", model="m2", mode="working") == {
        "parent": "fakep", "model": "m2", "provider": None, "mode": "working"}


def test_a_parent_table_in_gruntly_toml_does_not_break_a_spec(cfg):
    (cfg / ".gruntly.toml").write_text('harness = "generic"\n[parent]\nharness = "claude"\n')
    assert build_spec({"brief": "x", "acceptance": ["true"], "child_cmd": ["true"]}, cfg).brief == "x"


def test_delegating_is_the_default_and_the_flags_and_notes_reach_the_harness(cfg, capsys):
    assert cli.main(["agent", "--model", "big-one", "--provider", "openrouter", "fix", "it"]) == 0
    cap = capsys.readouterr()
    assert cap.out.strip() == "DELEGATED:big-one,openrouter:fix it" and "note: fake limit" in cap.err


def test_working_mode_runs_the_parent_as_a_worker_and_never_falls_back(cfg, capsys):
    FakeParent.reply = "GRUNTLY-FALLBACK: ignored in working mode"
    assert cli.main(["agent", "--mode", "working", "Fix it."]) == 0
    out = capsys.readouterr().out
    assert out.startswith("WORKED:Fix it.") and out.count("WORKED:") == 1
    assert "falling back" not in capsys.readouterr().err


def test_a_delegating_parent_that_asks_for_the_fallback_is_followed_by_a_working_session_that_is_told_why(cfg, capsys):
    FakeParent.reply = "GRUNTLY-FALLBACK: stuck after two rounds (run r_9)"
    assert cli.main(["agent", "Fix it."]) == 0
    cap = capsys.readouterr()
    assert "WORKED:Fix it." in cap.out and "could not finish it (stuck after two rounds (run r_9))" in cap.out and "falling back" in cap.err
    assert cli.main(["agent", "--no-fallback", "Fix it."]) == 0
    assert "WORKED:" not in capsys.readouterr().out


def test_settings_choose_the_harness_and_an_unknown_one_or_mode_is_a_clear_error(cfg, capsys):
    (cfg / "cfg" / "config.toml").write_text('[parent]\nharness = "other"\nmode = "working"\nmodel = "from-settings"\n')
    assert cli.main(["agent", "Fix it."]) == 0 and capsys.readouterr().out.startswith("WORKED:")
    assert cli.main(["agent", "--parent", "nope", "x"]) == 2
    assert "unknown parent harness 'nope'; known: fakep, other" in capsys.readouterr().err
    (cfg / "cfg" / "config.toml").write_text('[parent]\nmode = "lean"\n')
    assert cli.main(["agent", "x"]) == 2 and "mode must be one of delegating, working" in capsys.readouterr().err


def test_the_snippet_names_each_harnesss_file_and_fits_the_timeout_wording(capsys):
    from gruntly import cli
    assert cli.main(["init", "--snippet"]) == 0
    plain = capsys.readouterr().out
    assert "## Delegating to gruntly" in plain and "600000 ms Bash timeout" in plain and "<!--" not in plain             # the old output is unchanged
    for harness, file in (("claude", "CLAUDE.md"), ("codex", "AGENTS.md"), ("gemini", "GEMINI.md"), ("qwen", "QWEN.md"), ("opencode", "AGENTS.md"), ("hermes", "AGENTS.md")):
        assert cli.main(["init", "--snippet", "--for", harness]) == 0
        out = capsys.readouterr().out
        assert out.startswith(f"<!-- paste into {file} in your repository -->") and "## Delegating to gruntly" in out
        assert ("600000 ms Bash timeout" in out) == (harness == "claude") and (("gruntly wait RUN_ID" in out) == (harness != "claude"))
    assert cli.main(["init", "--snippet", "--for", "aider"]) == 2 and "cannot hand work to gruntly by itself" in capsys.readouterr().err
    assert cli.main(["init", "--snippet", "--for", "nope"]) == 2


def test_run_agent_says_what_the_parent_used_when_the_harness_reports_it_and_stays_quiet_when_it_does_not(monkeypatch, capsys):
    from gruntly import agent
    from gruntly.usage import Usage
    quiet = base.ParentOutcome("done")
    assert agent.parent_usage_line(quiet) is None and agent.parent_usage_line(base.ParentOutcome("x", usage=Usage())) is None
    line = agent.parent_usage_line(base.ParentOutcome("x", usage=Usage(prompt=2345, completion=67, cached=1000, requests=3), cost_usd=0.0123))
    assert line == "parent used 3 request(s), 2,345 prompt + 67 completion tokens (1,000 cached), $0.0123 as reported"
    assert agent.parent_usage_line(base.ParentOutcome("x", usage=Usage(prompt=5, completion=1, requests=1))) == "parent used 1 request(s), 5 prompt + 1 completion tokens"
