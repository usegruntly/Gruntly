"""Coverage facts: counting how much of the request the diff covers, with no model."""
import subprocess

import pytest

from gruntly import agent, coverage, trace


def git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)


def patch(*paths, added="x = 1"):
    return "".join(f"diff --git a/{p} b/{p}\n--- a/{p}\n+++ b/{p}\n@@ -0,0 +1 @@\n+{added}\n" for p in paths)


@pytest.fixture
def proj(tmp_path):
    r = tmp_path / "p"
    (r / "app").mkdir(parents=True)
    (r / "tests").mkdir()
    for n in "abcdefg":
        (r / "app" / f"{n}.py").write_text(f"import os\nX_{n} = os.environ.get('APP_{n.upper()}')\n")
    (r / "app" / "config.py").write_text("")
    (r / "tests" / "test_a.py").write_text("def test_x():\n    pass\n")
    (r / "CHANGES.rst").write_text("changes\n")
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")
    return r


def test_parts_counts_numbered_and_lettered_items():
    assert coverage.parts("Do it. (1) store it (2) the model (3) the service (4) the CLI") == 4
    assert coverage.parts("Steps:\n1. one\n2. two\n3) three") == 3
    assert coverage.parts("(A) first (B) second") == 2
    assert coverage.parts("Add a level. Storage: keep it with the product. API: add(name, level). CLI: a low command.") == 3
    assert coverage.parts("Fix it. Note: see the docs. Example: x. Why: y.") == 0
    assert coverage.parts("Fix the off-by-one in paginate() (see issue 12).") == 0


def test_patch_files_and_added_text():
    p = patch("a/x.py", "b.py", added="y = 2")
    assert coverage.patch_files(p) == ["a/x.py", "b.py"]
    assert coverage.added_text(p) == "y = 2\ny = 2"


def test_named_paths_are_tracked_non_test_files_only(proj):
    files = ["app/a.py", "tests/test_a.py"]
    assert coverage.named_paths("change app/a.py, tests/test_a.py and nope.py", files) == ["app/a.py"]


def test_code_names_skip_english_builtins_and_usage_lines():
    names = coverage.code_names("Add `low_stock` and reorder_level; raise ValueError for a bad `--json`. "
                                "The CLI takes `add NAME QTY PRICE [LEVEL]`. Use `load()` and the HelpFormatter. Be sure.")
    assert {"low_stock", "reorder_level", "--json", "load", "HelpFormatter"} <= set(names)
    assert "ValueError" not in names and "LEVEL" not in names and "NAME" not in names and "sure" not in names


def test_a_request_with_many_parts_and_one_changed_file_is_flagged(proj):
    req = "Add a level. (1) store it (2) the model (3) low_stock() (4) the CLI"
    out = coverage.facts(req, patch("app/a.py"), proj)
    assert any("4 parts" in f and "1 source file" in f and "app/a.py" in f for f in out)
    assert not any("4 parts" in f for f in coverage.facts(req, patch("app/a.py", "app/b.py", "app/c.py", "app/d.py"), proj))


def test_a_named_file_the_diff_never_touches_is_flagged(proj):
    out = coverage.facts("Change app/a.py to read its setting", patch("app/b.py"), proj)
    assert any("names app/a.py" in f and "does not touch it" in f for f in out)
    assert not any("names app/a.py" in f for f in coverage.facts("Change app/a.py to read its setting", patch("app/a.py"), proj))


def test_a_request_about_many_modules_with_one_file_changed_is_flagged(proj):
    req = "Every other module must use load() instead of reading the environment."
    out = coverage.facts(req, patch("app/config.py", added="def load(): pass"), proj)
    assert any("many modules" in f and "1 of 8" in f for f in out)
    five = patch("app/a.py", "app/b.py", "app/c.py", "app/d.py", "app/e.py", added="def load(): pass")
    assert not any("many modules" in f for f in coverage.facts(req, five, proj))


def test_a_name_the_request_asks_for_that_exists_nowhere_is_flagged(proj):
    req = "Add `low_stock` and `reorder_level`; keep `X_a` as it is."
    out = coverage.facts(req, patch("app/a.py", added="def reorder_level(): pass"), proj)
    assert any("low_stock" in f and "reorder_level" not in f and "X_a" not in f for f in out)


def test_a_diff_that_only_changes_a_changelog_is_flagged(proj):
    out = coverage.facts("Fix `write_usage` for empty arguments.", patch("CHANGES.rst", added="- fixed"), proj)
    assert any("only non-code files (CHANGES.rst)" in f for f in out)


def test_nothing_stands_out_when_the_diff_covers_the_request(proj):
    assert coverage.facts("Make app/a.py read APP_A at call time.", patch("app/a.py", added="APP_A = 1"), proj) == []
    assert coverage.facts("", patch("app/a.py"), proj) == [] and coverage.facts("x", "", proj) == []


def test_facts_are_capped(proj):
    req = ("`new_one` `new_two` `new_three` (1) a (2) b (3) c every other module app/a.py app/b.py app/c.py")
    assert len(coverage.facts(req, patch("CHANGES.rst"), proj)) <= coverage.MAX_FACTS


def test_the_block_carries_the_facts_only_when_given_a_root(proj):
    res = {"run_id": "r_1", "status": "passed", "applied": True, "attempts": 1, "verify": "unchanged",
           "diff_stat": {"paths": ["app/a.py"], "insertions": 1, "deletions": 0}, "gates": {}}
    req = "Add a level. (1) store it (2) the model (3) low_stock() (4) the CLI"
    with_root = agent.block(res, None, patch=patch("app/a.py"), request=req, root=proj)
    assert "flags:" in with_root and "4 parts" in with_root
    assert "4 parts" not in agent.block(res, None, patch=patch("app/a.py"), request=req)


def test_the_lean_prompt_points_at_the_flags_and_keeps_to_shell_safe_text():
    assert "flags say the request lists parts" in agent.LEAN_PROMPT
    assert '"' not in agent.LEAN_PROMPT and "<" not in agent.LEAN_PROMPT and ">" not in agent.LEAN_PROMPT


def test_a_child_that_edited_without_running_a_test_is_a_concern():
    t = {"calls": 3, "kinds": {"read": 2, "edit": 1}, "failed": 0, "test_runs": 0, "max_repeat": 1}
    assert any("ran no test" in c for c in trace.concerns(t))
    assert not any("ran no test" in c for c in trace.concerns({**t, "test_runs": 1}))
    assert not any("ran no test" in c for c in trace.concerns({**t, "kinds": {"read": 3}}))


def test_gaps_say_what_kind_of_gap_each_fact_is(proj):
    kinds = [k for k, _ in coverage.gaps("Add a level. (1) a (2) b (3) c", patch("app/a.py"), proj)]
    assert kinds == ["parts"] and set(kinds) <= coverage.STRONG
    assert [k for k, _ in coverage.gaps("Change app/a.py to read its setting", patch("app/b.py"), proj)] == ["named"]
    assert "named" not in coverage.STRONG                       # a named file may be only a reference: never grounds to escalate


def test_the_cumulative_patch_has_edits_and_new_files_since_the_base(proj):
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=proj, check=True, capture_output=True, text=True).stdout.strip()
    (proj / "app" / "a.py").write_text("import os\nX_a = 2\n")               # an edit
    (proj / "app" / "new_mod.py").write_text("def load():\n    return 1\n")   # a new, untracked file
    (proj / ".gruntly").mkdir()
    (proj / ".gruntly" / "noise.json").write_text("{}")                      # gruntly's own state is not the child's work
    out = coverage.cumulative_patch(proj, base)
    assert coverage.patch_files(out) == ["app/a.py", "app/new_mod.py"]
    assert "def load():" in coverage.added_text(out)


def test_a_name_that_a_rename_removes_is_a_hint_not_grounds_to_escalate(proj):
    """Renaming customer_label to account_label leaves customer_label nowhere: that is success, not a gap."""
    req = "Rename customer_label to account_label everywhere in app."
    out = coverage.gaps(req, patch("app/a.py", "app/b.py", "app/c.py", "app/d.py", "app/e.py", added="account_label = 1"), proj)
    assert any(k == "names" and "customer_label" in t for k, t in out)       # still shown in the flags
    assert "names" not in coverage.STRONG and not [k for k, _ in out if k in coverage.STRONG]


def test_a_path_outside_the_project_is_not_a_name_the_diff_should_have_added():
    """Website session, 2026-11-13: a request that pointed at a scratch file by its absolute path made the block warn that the diff 'never adds
    head_block, AppData'."""
    win = r"Copy the five lines from C:\Users\someone\AppData\Local\Temp\scratch\head_block.txt into `page.html` after the viewport meta."
    posix = "Copy the lines from /tmp/pytest_work/head_block.txt into page.html, using set_title()."
    assert "head_block" not in coverage.code_names(win) and "AppData" not in coverage.code_names(win)
    assert "head_block" not in coverage.code_names(posix) and "set_title" in coverage.code_names(posix)      # a real name beside the path stays
    assert "head_block" in coverage.code_names("Fix head_block in src/api/user_client.py")                       # a name in the project still counts
    assert "user_client" in coverage.code_names("Fix get_user in src/api/user_client.py")                        # and a relative path is not mistaken for one outside
