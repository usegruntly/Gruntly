"""Issue #6: a child that edits the person's own tree (or writes next to it) instead of its worktree. The gate fails the run; `gruntly restore` puts the files back,
but only the ones that are still exactly as the child left them."""
import json

from gruntly import cli, prompt, worktree as wtmod
from gruntly.spec import Spec

from tests.conftest import sh


def _run_cli(capsys, *argv):
    assert cli.main(list(argv)) == 0
    return json.loads(capsys.readouterr().out)


def _leak(run_task, make_spec, monkeypatch, scenario="main_tree"):
    res, root = run_task(make_spec(scenario, max_attempts=1, allowed_paths=["calc.py", "**"]))
    monkeypatch.chdir(root)
    return res, root


def test_a_file_the_child_created_in_the_main_tree_is_reported_and_restore_takes_it_away(run_task, make_spec, monkeypatch, capsys):
    res, root = _leak(run_task, make_spec, monkeypatch)
    assert res["status"] == "escalate" and any("main tree modified: leaked.txt" in v for v in res["gates"]["scope"]["violations"])
    assert "main_tree" not in res["gates"]["scope"]                                    # the bookkeeping never reaches the compact result
    assert any("leaked.txt" in w and f"gruntly restore {res['run_id']}" in w for w in res["warnings"])
    rid = res["run_id"]
    dry = _run_cli(capsys, "restore", rid, "--dry-run")
    assert dry["would_restore"] == ["leaked.txt"] and (root / "leaked.txt").exists()      # a dry run changes nothing
    done = _run_cli(capsys, "restore", rid)
    assert done["restored"] == ["leaked.txt"] and not (root / "leaked.txt").exists()
    assert sh(root, "git", "status", "--porcelain").stdout.strip() == ""
    again = _run_cli(capsys, "restore", rid)                                            # running it twice is harmless
    assert again["restored"] == [] and again["left_alone"][0]["why"] == "already as it was before the run"


def test_a_tracked_file_the_child_edited_and_one_it_deleted_come_back_exactly_as_they_were(run_task, make_spec, monkeypatch, capsys):
    res, root = _leak(run_task, make_spec, monkeypatch, "main_tree_edit")
    original = sh(root, "git", "show", "HEAD:calc.py").stdout
    assert (root / "calc.py").read_text() != original
    assert _run_cli(capsys, "restore", res["run_id"])["restored"] == ["calc.py"]
    assert (root / "calc.py").read_text() == original and sh(root, "git", "status", "--porcelain").stdout.strip() == ""
    res, root = _leak(run_task, make_spec, monkeypatch, "main_tree_delete")
    assert not (root / "test_calc.py").exists()
    assert _run_cli(capsys, "restore", res["run_id"])["restored"] == ["test_calc.py"]
    assert (root / "test_calc.py").read_text() == sh(root, "git", "show", "HEAD:test_calc.py").stdout


def test_a_file_edited_after_the_run_is_never_touched(run_task, make_spec, monkeypatch, capsys):
    res, root = _leak(run_task, make_spec, monkeypatch)
    (root / "leaked.txt").write_text("my own notes now\n")                              # the person (or the parent) kept working in the file
    out = _run_cli(capsys, "restore", res["run_id"])
    assert out["restored"] == [] and out["left_alone"] == [{"path": "leaked.txt", "why": "edited again since the run; left alone"}]
    assert (root / "leaked.txt").read_text() == "my own notes now\n"


def test_a_run_with_nothing_to_restore_and_a_bad_id_say_so(run_task, make_spec, monkeypatch, capsys):
    res, root = run_task(make_spec("pass"))
    monkeypatch.chdir(root)
    assert "nothing to restore" in _run_cli(capsys, "restore", res["run_id"])["error"]
    assert _run_cli(capsys, "restore", "r_x/../../y")["error"] == "not a run id"


def test_the_saved_trees_are_dropped_by_gc_once_they_are_old_enough(run_task, make_spec, monkeypatch, capsys):
    res, root = _leak(run_task, make_spec, monkeypatch)
    assert wtmod.prune_main_trees(root, days=14) == 0                                   # fresh: kept
    assert wtmod.prune_main_trees(root, days=-1) == 2                                   # before and after
    assert "nothing to restore" in _run_cli(capsys, "restore", res["run_id"])["error"]


def test_a_file_written_next_to_the_repository_is_a_warning_not_a_failure(run_task, make_spec):
    res, root = run_task(make_spec("stray_file"))
    assert res["status"] == "passed" and any("stray_fix.py" in w and "outside" in w for w in res["warnings"])
    assert (root.parent / "stray_fix.py").exists()                                       # gruntly never deletes outside the repository


def test_the_child_is_told_its_exact_working_directory(run_task, make_spec):
    res, _ = run_task(make_spec("named_cwd", max_attempts=1))
    assert "CWD-OK" in json.dumps(res), res


def test_the_prompts_name_the_directory_only_when_they_are_given_one():
    spec = Spec(brief="Fix add().")
    for fn in (prompt.first, lambda s, cwd=None: prompt.continuation(s, "", "", cwd=cwd), lambda s, cwd=None: prompt.resume_fresh(s, "acceptance", "x", cwd=cwd)):
        assert "Your working directory is /w/x. Read and write only inside it" in fn(spec, cwd="/w/x")
        assert "working directory" not in fn(spec)
    research = Spec(brief="What?", kind="research")
    assert "Your working directory is /w/x." in prompt.first(research, cwd="/w/x")
