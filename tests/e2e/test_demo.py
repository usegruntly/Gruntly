"""`gruntly demo`: three toy tasks through the real runner with a stand-in child (no model, key or network), which doubles as a smoke test of an install."""
import os
from pathlib import Path

from gruntly import cli, demo
from gruntly.store import force_rmtree


def test_the_offline_demo_shows_the_pass_the_weakened_test_and_the_leak_and_exits_zero(capsys):
    assert cli.main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "no model, no key, no network" in out
    assert "1/3" in out and "result: passed (1 file, +1 -1)" in out
    assert "test_weakening FAILED" in out and "existing test edited: test_calc.py" in out
    assert "main tree modified: notes.txt" in out and "restored: notes.txt; notes.txt is now in your tree: False" in out
    assert "All three behaved as designed" in out


def test_the_demo_leaves_no_toy_repository_unless_asked_and_never_changes_your_environment(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("GRUNTLY_STATE_DIR", str(tmp_path / "mine"))
    monkeypatch.delenv("GRUNTLY_CONFIG_DIR", raising=False)
    assert cli.main(["demo"]) == 0
    out = capsys.readouterr().out
    toy = Path(out.split("toy repository: ", 1)[1].splitlines()[0].split(" (add()")[0])
    assert not toy.exists() and "kept:" not in out
    assert os.environ["GRUNTLY_STATE_DIR"] == str(tmp_path / "mine") and "GRUNTLY_CONFIG_DIR" not in os.environ
    assert not (tmp_path / "mine").exists()                                             # the demo used a state folder of its own
    assert cli.main(["demo", "--keep"]) == 0
    kept = Path(capsys.readouterr().out.rsplit("kept: ", 1)[1].splitlines()[0].strip())
    try:
        assert (kept / "toy" / "calc.py").exists()
    finally:
        force_rmtree(kept)


def test_a_scenario_that_does_not_behave_as_designed_is_reported_and_the_exit_code_says_so(capsys, monkeypatch):
    monkeypatch.setattr(demo, "TEST", "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 6\n\n\nif __name__ == \"__main__\":\n    test_add()\n    print(\"ok\")\n")
    assert cli.main(["demo"]) == 1                                                       # task 1 can never pass with this test
    out = capsys.readouterr().out
    assert "NOT as designed" in out and "task 1 should pass" in out and "All three behaved" not in out


def test_the_version_flag_prints_the_installed_version(capsys):
    import re
    import pytest
    with pytest.raises(SystemExit) as stop:
        cli.main(["--version"])
    assert stop.value.code == 0 and re.fullmatch(r"gruntly \d+\.\d+\.\d+\S*\n", capsys.readouterr().out)


def test_the_live_demo_says_what_to_check_when_the_chain_does_not_work(capsys, monkeypatch):
    monkeypatch.setattr(demo, "_run", lambda repo, raw: ({"status": "error", "error": "model server unreachable", "gates": {}}, "r_x", repo))
    assert cli.main(["demo", "--live"]) == 1
    out = capsys.readouterr().out
    assert "model server unreachable" in out and "gruntly doctor" in out and "gruntly setup" in out
