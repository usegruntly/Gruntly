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
    monkeypatch.setattr(parents, "pick_installed", lambda: "fakep")
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
