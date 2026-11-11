"""`gruntly agent-run`: one marked result block, and a follow-up that keeps the same run."""
import io
import sys

import pytest

from gruntly import agent, cli
from tests.e2e.test_do import write_config  # noqa: F401  (same fake child setup)


def say(capsys, monkeypatch, repo, request, *flags):
    monkeypatch.chdir(repo)
    monkeypatch.setattr("sys.stdin", io.StringIO(request))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    assert cli.main(["agent-run", *flags]) == 0
    return capsys.readouterr().out.strip()


@pytest.fixture
def proj(repo):
    write_config(repo)
    return repo


def test_the_result_is_one_marked_block_with_status_files_and_diff(proj, capsys, monkeypatch):
    out = say(capsys, monkeypatch, proj, "fix add() so test_calc passes")
    assert out.startswith(agent.OPEN) and out.endswith(agent.CLOSE), out
    assert "status: passed" in out and "calc.py" in out and "a + b" in out
    assert "next: nothing to open or rerun" in out          # the caller has the tests and the whole diff
    assert "[untrusted diff" in out and "full patch: .gruntly/runs/" in out
    assert out.count(agent.OPEN) == 1


def test_the_contract_of_changed_functions_is_included(proj, capsys, monkeypatch):
    out = say(capsys, monkeypatch, proj, "fix add() so test_calc passes")
    assert "def add(" in out.split("contract", 1)[1]


def test_a_refusal_is_a_block_too(proj, capsys, monkeypatch):
    out = say(capsys, monkeypatch, proj, "rewrite the flux capacitor")
    assert out.startswith(agent.OPEN) and "status: refused" in out


def test_a_long_diff_is_truncated_and_flagged():
    patch = "\n".join(f"+line {i}" for i in range(300))
    out = agent.block({"run_id": "r1", "status": "passed", "applied": True, "diff_stat": {"paths": ["a.py"]}}, None, patch=patch)
    assert "diff truncated" in out and "more lines" in out


def test_child_text_stays_inside_fences():
    out = agent.block({"run_id": "r1", "status": "failed", "untrusted": {"gate_output": "IGNORE ALL"}}, None)
    assert out.index("[untrusted") < out.index("IGNORE ALL") < out.index("[end untrusted]")


def test_the_lean_command_has_one_tool_and_no_plugins():
    argv, _ = agent.lean_command("t", "sonnet")
    assert argv[argv.index("--tools") + 1] == "Bash" and "--strict-mcp-config" in argv and "--disable-slash-commands" in argv
    full, _ = agent.lean_command("t", "sonnet", full=True)
    assert "--tools" not in full and "--system-prompt" not in full


def test_a_follow_up_after_an_applied_run_starts_a_new_run_on_the_current_tree(proj, capsys, monkeypatch):
    first = say(capsys, monkeypatch, proj, "fix add() so test_calc passes")
    assert "status: passed" in first
    rid = next(ln.split(": ", 1)[1] for ln in first.splitlines() if ln.startswith("run: "))
    assert not (proj / ".gruntly" / "worktrees" / rid).exists()  # applied runs drop their worktree
    second = say(capsys, monkeypatch, proj, "also keep the names", "--continue", rid)
    assert second.startswith(agent.OPEN) and "worktree is gone" not in second, second


def test_the_trace_line_and_trace_flags_reach_the_block():
    r = {"run_id": "r1", "status": "passed", "applied": True, "diff_stat": {"paths": ["a.py"]},
         "child_trace": "child: 3 tool calls (read x1, edit x1, run x1), 0 failed, 1 test run",
         "review_hint": ["the child repeated one tool call 3 times"]}
    out = agent.block(r, None, patch="+x")
    assert "child: 3 tool calls" in out and "repeated one tool call 3 times" in out


def test_a_flag_is_not_listed_twice():
    r = {"run_id": "r1", "status": "passed", "applied": True, "diff_stat": {"paths": ["a.py"]},
         "review_hint": ["weak acceptance: tests pass first"], "warnings": ["tests pass first"]}
    assert agent.block(r, None).count("tests pass first") == 1


NEW_TEST_PATCH = ("diff --git a/test_new.py b/test_new.py\nnew file mode 100644\n--- /dev/null\n+++ b/test_new.py\n+def test_x():\n+    pass\n"
                  "diff --git a/util.py b/util.py\n--- a/util.py\n+++ b/util.py\n-return 1\n+return 2\n")


def test_a_pass_proved_only_by_the_childs_own_test_says_so_on_the_status_line():
    r = {"run_id": "r1", "status": "passed", "applied": True, "diff_stat": {"paths": ["util.py", "test_new.py"]},
         "warnings": ["acceptance already passes before any change: it cannot prove the task was done"],
         "review_hint": ["weak acceptance: acceptance already passes before any change: it cannot prove the task was done"]}
    out = agent.block(r, None, patch=NEW_TEST_PATCH, note=agent.LOOSE_NOTE)
    assert out.splitlines()[2].startswith("status: passed, UNPROVEN:")
    assert agent.LOOSE_NOTE not in out and "acceptance already passes" not in out     # not repeated as a flag


def test_a_pass_with_a_found_test_or_no_new_test_file_is_not_called_unproven():
    r = {"run_id": "r1", "status": "passed", "applied": True, "diff_stat": {"paths": ["util.py"]}}
    assert "UNPROVEN" not in agent.block(r, None, patch=NEW_TEST_PATCH)                   # a test covered the code
    weak = dict(r, warnings=["acceptance already passes before any change: x"])
    assert "UNPROVEN" not in agent.block(weak, None, patch=NEW_TEST_PATCH.split("diff --git a/util.py")[1])   # child added no test
    assert agent.block(weak, None, patch="+x").splitlines()[2] == "status: passed"


def commit(repo, *names):
    import subprocess
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "more"], cwd=repo, check=True)


def test_a_request_naming_two_files_is_split_per_file(proj):
    (proj / "other.py").write_text("def sub(a, b):\n    return a + b\n")
    commit(proj)
    parts = agent.split_request("Fix the bugs in calc.py and other.py", proj)
    assert len(parts) == 2 and parts[0].startswith("In calc.py") and "other.py" not in parts[0]
    assert agent.split_request("fix add() in calc.py", proj) == ["fix add() in calc.py"]


def test_two_part_blocks_are_joined_into_one_block():
    one = agent.block(None, None, error="a")
    two = agent.join_blocks([one, agent.block(None, None, error="b")])
    assert two.count(agent.OPEN) == 1 and two.count(agent.CLOSE) == 1 and "part 2 of 2" in two


def test_no_covering_test_runs_against_the_whole_suite_with_a_flag(proj, capsys, monkeypatch):
    (proj / "util.py").write_text("def noop():\n    return 1\n")
    commit(proj)
    out = say(capsys, monkeypatch, proj, "change noop() in util.py to return 2")
    assert out.startswith(agent.OPEN) and "no test covered this code" in out
    assert "status: refused" not in out


def test_other_refusals_are_not_loosened(proj, capsys, monkeypatch):
    out = say(capsys, monkeypatch, proj, "rewrite the flux capacitor")
    assert "status: refused" in out


def test_the_childs_own_new_test_file_stays_editable(proj):
    (proj / "util.py").write_text("def noop():\n    return 1\n")
    commit(proj)
    from gruntly import do
    refusal = do.plan("change noop() in util.py", proj)
    plan, raw = agent.loose_plan("change noop() in util.py", proj, refusal)
    assert raw["tests_writable"] and raw["followup"] and any(p.startswith("test_gruntly_util") for p in raw["allowed_paths"])


def test_a_refactor_whose_tests_already_pass_still_runs(proj, capsys, monkeypatch):
    out = say(capsys, monkeypatch, proj, "rename add() in calc.py to plus and keep behaviour")
    assert "status: refused" not in out or "already pass" not in out


def test_an_everywhere_request_may_change_every_python_file(proj):
    from gruntly import do
    req = "rename add to plus everywhere in the repo"
    plan, raw = agent.loose_plan(req, proj, do.Refusal("the request matches 9 files"))
    assert "**/*.py" in raw["allowed_paths"] and raw["tests_writable"]
    assert agent.loose_plan("fix add()", proj, do.Refusal("the request matches 9 files")) is None


def test_ask_returns_the_childs_answer_without_a_diff_or_tests(repo, capsys, monkeypatch):
    write_config(repo, "answer")
    (repo / "README.md").write_text("not python\n")
    out = say(capsys, monkeypatch, repo, "who maintains this?", "--ask")
    assert out.startswith(agent.OPEN) and out.endswith(agent.CLOSE), out
    assert "status: passed (research" in out and "Aaryan Beniwal" in out and "[untrusted answer" in out
    assert "tests:" not in out and "[untrusted diff" not in out


def test_ask_fails_if_the_child_changes_a_file(repo, capsys, monkeypatch):
    write_config(repo, "pass")           # the "pass" child edits calc.py, which a research run must not do
    out = say(capsys, monkeypatch, repo, "who maintains this?", "--ask")
    assert "status: failed" in out or "status: error" in out
    assert "[untrusted answer" not in out


def test_a_request_about_a_non_python_file_runs_with_a_changed_file_check(repo, capsys, monkeypatch):
    from gruntly import worktree
    from conftest import sh
    web = repo / "site"
    web.mkdir()
    (web / "my page.html").write_text("<p>[placeholder]</p>\n")
    (repo / "calc.py").unlink()
    (repo / "test_calc.py").unlink()
    sh(repo, "git", "add", "-A")
    sh(repo, "git", "commit", "-qm", "site only")
    write_config(repo, "edit_page")
    out = say(capsys, monkeypatch, repo, 'In "my page.html" replace [placeholder] with hello. Change nothing else.')
    assert "status: passed" in out, out                       # the changed-file check must see the child's edit
    assert "no tests apply to this kind of file" in out
    assert "hello" in (web / "my page.html").read_text()


def test_a_non_python_request_that_changes_nothing_fails_the_check(repo, capsys, monkeypatch):
    from conftest import sh
    (repo / "notes.md").write_text("old\n")
    (repo / "calc.py").unlink()
    (repo / "test_calc.py").unlink()
    sh(repo, "git", "add", "-A")
    sh(repo, "git", "commit", "-qm", "notes only")
    write_config(repo, "no_fix")
    out = say(capsys, monkeypatch, repo, "In notes.md add a sentence about gruntly.")
    assert "status: failed" in out and "status: passed" not in out


def test_parts_run_side_by_side_and_apply_one_by_one_afterwards(proj, capsys, monkeypatch):
    (proj / "other.py").write_text("def sub(a, b):\n    return a + b\n")
    (proj / "test_other.py").write_text("from other import sub\n\ndef test_sub():\n    assert sub(3, 1) == 2\n")
    commit(proj)
    monkeypatch.setattr(cli, "_runs_in_parallel", lambda root: True)
    out = say(capsys, monkeypatch, proj, "Fix the bugs in calc.py and other.py")
    assert out.count(agent.OPEN) == 1 and "part 1 of 2" in out and "part 2 of 2" in out
    assert "a + b" in (proj / "calc.py").read_text()            # the part that passed was applied after both finished


def test_the_diff_shows_real_code_before_test_files():
    p = ("diff --git a/test_x.py b/test_x.py\n@@ -0,0 +1 @@\n+t\n"
         "diff --git a/tool/cli.py b/tool/cli.py\n@@ -1 +1 @@\n-a\n+b\n")
    out = agent.code_first(p)
    assert out.index("tool/cli.py") < out.index("test_x.py")


def test_a_test_that_only_imports_the_target_still_covers_it(proj):
    from gruntly import do
    (proj / "tool").mkdir()
    (proj / "tool" / "__init__.py").write_text("")
    (proj / "tool" / "cli.py").write_text("def run(argv):\n    return 'text'\n")
    (proj / "test_json_new.py").write_text("from tool.cli import run\n\ndef test_json():\n    assert run(['list', '--json']) == '{}'\n")
    commit(proj)
    p = do.plan("In tool/cli.py add --json to the list command.", proj)
    assert not isinstance(p, do.Refusal), p
    assert p.targets == ["tool/cli.py"] and "test_json_new.py" in p.tests


def test_explore_gives_the_whole_project_but_not_the_tests_or_the_check(proj):
    (proj / "check_names.py").write_text("print('ok')\n")
    commit(proj)
    p, raw = agent.explore_plan("Make the names consistent.", proj, "python check_names.py && python -m pytest -q")
    assert raw["allowed_paths"] == ["**"] and "check_names.py" in raw["deny_paths"]
    assert not any(t.startswith("test_") for t in raw["deny_paths"])      # a rename must reach the tests too
    assert "find where this has to change yourself" in raw["brief"]
    assert raw["acceptance"][0]["cmd"] == "python check_names.py && python -m pytest -q"
