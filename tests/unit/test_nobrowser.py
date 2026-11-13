"""Nothing gruntly launches unattended may open a browser tab (gruntly/nobrowser.py): Aider's `--yes-always` answers yes to "Open URL for more info?"."""
import os
import subprocess
import sys

from gruntly import nobrowser
from gruntly.adapters import base as child_base
from gruntly.parents import base as parent_base

OPEN_ONE = "import sys, webbrowser; sys.exit(0 if webbrowser.open('https://example.test/docs#notes') else 1)"


def test_the_value_runs_the_program_it_names_with_the_url_last_even_in_a_folder_with_a_space(tmp_path):
    rec = tmp_path / "a folder" / "record.py"
    rec.parent.mkdir()
    rec.write_text("import sys\nopen(sys.argv[1], 'a').write(' '.join(sys.argv[2:]) + '\\n')\n")
    log = tmp_path / "log.txt"
    value = nobrowser.env([sys.executable, str(rec), str(log)])["BROWSER"]
    r = subprocess.run([sys.executable, "-c", OPEN_ONE], env={**os.environ, "BROWSER": value}, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr                                               # webbrowser.open answered True: the stand-in ran and succeeded
    assert log.read_text().split() == ["https://example.test/docs#notes"]            # and it, not a browser, was handed the URL


def test_the_default_program_does_nothing_and_succeeds():
    value = nobrowser.env()["BROWSER"]
    assert value.endswith(" %s") and value.startswith('"') and "\\" not in value
    r = subprocess.run([sys.executable, "-c", OPEN_ONE], env={**os.environ, "BROWSER": value}, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""


def test_a_caller_can_allow_browsers_for_a_harness_that_has_to_sign_in_through_one(monkeypatch):
    monkeypatch.setenv(nobrowser.ALLOW, "1")
    assert nobrowser.env() == {}
    assert child_base.scrub_env({}).get("BROWSER") is None


def test_every_child_gets_it_unless_its_adapter_sets_its_own():
    assert child_base.scrub_env({})["BROWSER"] == nobrowser.command()
    assert child_base.scrub_env({"BROWSER": "mine %s"})["BROWSER"] == "mine %s"


def test_every_launched_parent_gets_it_and_a_caller_can_still_override(tmp_path):
    from tests.unit.test_parents import ScriptParent
    code = "import os; print(os.environ['BROWSER'])"
    r = parent_base.run(ScriptParent(code), "t", "working", cwd=tmp_path)
    assert r.outcome.final_message == nobrowser.command()
    r = parent_base.run(ScriptParent(code), "t", "working", cwd=tmp_path, env={"BROWSER": "mine %s"})
    assert r.outcome.final_message == "mine %s"


def test_every_test_runs_with_it_so_a_real_binary_under_test_cannot_open_a_tab():
    assert os.environ["BROWSER"] == nobrowser.command()
