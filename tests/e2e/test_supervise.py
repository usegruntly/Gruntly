"""`agent-run --supervised`: the child plans, a fresh child does each step, a reviewer (stubbed here) judges each one."""
from gruntly import cli, rules as rulesmod, supervise
from tests.e2e.test_do import write_config


def start(repo, request="Make add() in calc.py add.", check=None):
    sid = supervise.new_id()
    supervise._write(supervise.sup_dir(repo, sid), "task.json", {"request": request, "check": check, "model": None})
    return sid


class Reviewer:
    """Scripted replies, recording what the reviewer was shown."""
    def __init__(self, *replies):
        self.replies, self.seen, self.systems, self.caches = list(replies), [], [], []

    def __call__(self, text, model, timeout_s=300, system_file=None, cache=True):
        system = system_file.read_text(encoding="utf8") if system_file else ""
        self.seen.append(system + "\n\n" + text)         # what the reviewer knew: its system prompt and the message
        self.systems.append(system)
        self.caches.append(cache)
        return self.replies.pop(0) if self.replies else "APPROVE: ok", 0.002


def prompts(repo):
    return [p.read_text(encoding="utf8") for p in sorted((repo / ".gruntly" / "runs").glob("*/attempts/1/prompt.txt"),
                                                         key=lambda p: p.stat().st_mtime)]


def test_the_child_plans_a_fresh_child_does_the_step_and_the_reviewer_approves(repo):
    write_config(repo, "supervised")
    (repo / "AGENTS.md").write_text("Use four spaces.\n")
    rulesmod.add(repo, "Do not rename add()")
    rev = Reviewer("APPROVE", "APPROVE: add() now returns a + b")
    block = supervise.run(repo, start(repo, check="python -m pytest -q -p no:cacheprovider"), call=rev)
    assert "status: passed" in block and "step 1: approved after 1 run(s): add() now returns a + b" in block
    assert "reviewer: 2 calls" in block and "check in your working tree: pass" in block
    assert "a + b" in (repo / "calc.py").read_text()
    # the reviewer saw the person's rules, the project's AGENTS.md, the plan, the diff and the child's report
    assert "Do not rename add()" in rev.seen[0] and "Use four spaces." in rev.seen[0] and "1. Fix add()" in rev.seen[0]
    assert "return a + b" in rev.seen[1] and "REPORT: read calc.py" in rev.seen[1]
    # the step's child got the plan, its one step, the rules, and was asked for a report
    step = prompts(repo)[-1]
    assert "YOUR STEP, AND ONLY THIS STEP: 1." in step and "Do not rename add()" in step and "REPORT:" in step


def test_a_fix_goes_to_a_fresh_child_with_the_reviewers_words(repo):
    write_config(repo, "supervised")
    rev = Reviewer("APPROVE", "FIX: also handle negative numbers", "APPROVE: done")
    block = supervise.run(repo, start(repo), call=rev)
    assert "status: passed" in block and "approved after 2 run(s)" in block
    assert "also handle negative numbers" in prompts(repo)[-1] and "already in the code" in prompts(repo)[-1]


def test_the_reviewer_can_revise_the_plan_or_stop(repo):
    write_config(repo, "supervised")
    rev = Reviewer("REVISE\n1. Fix add() in calc.py.\n2. Check nothing else uses subtraction.", "APPROVE: a", "STOP: step 2 is not needed")
    block = supervise.run(repo, start(repo), call=rev)
    assert "status: failed (step 2 stopped)" in block and "step 1: approved" in block
    assert "approved steps stay applied" in block
    assert "step 2 is not needed" in block and "quoting the reviewer" in block      # the words travel with the failure


def test_wait_and_cli_wait_return_the_block_or_a_running_note(repo, capsys, monkeypatch):
    monkeypatch.chdir(repo)
    sid = start(repo)
    assert "status: running" in supervise.wait(repo, sid, 0) and f"gruntly wait {sid}" in supervise.wait(repo, sid, 0)
    supervise._write(supervise.sup_dir(repo, sid), "block.txt", "=== GRUNTLY RESULT ===\nstatus: passed\n=== END ===")
    assert cli.main(["wait", sid, "--timeout", "1"]) == 0
    assert "status: passed" in capsys.readouterr().out


def test_steps_are_parsed_from_a_numbered_plan():
    text = "Plan:\n1. Find the bug\n   in calc.py\n2) Fix it\nStep 3: test it\nnot a step"
    assert supervise.parse_steps(text) == ["Find the bug in calc.py", "Fix it", "test it"]
    assert supervise.verdict("Looks fine. APPROVE: done") == ("APPROVE", "done")
    assert supervise.verdict("hmm") [0] == "FIX"


def test_the_reviewer_sees_its_own_earlier_feedback_on_a_step(repo):
    write_config(repo, "supervised")
    rev = Reviewer("APPROVE", "FIX: keep the guard for n <= 0", "APPROVE: done")
    supervise.run(repo, start(repo), call=rev)
    assert "YOUR EARLIER FEEDBACK ON THIS STEP" in rev.seen[2] and "keep the guard for n <= 0" in rev.seen[2]
    assert "do not ask to undo that" in rev.seen[1]
    assert "list them in your REPORT; do not fix them" in prompts(repo)[-1]


def test_a_step_with_nothing_left_to_do_shows_the_reviewer_the_code_as_it_is(repo):
    import subprocess
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n")     # already done before the step runs
    subprocess.run(["git", "commit", "-qam", "already fixed"], cwd=repo, check=True)
    write_config(repo, "supervised")
    rev = Reviewer("APPROVE", "APPROVE: already correct")
    block = supervise.run(repo, start(repo), call=rev)
    assert "status: passed" in block
    assert "THE FILES THIS STEP NAMES, AS THEY ARE NOW" in rev.seen[1] and "return a + b" in rev.seen[1]


def test_the_plan_and_the_steps_go_to_different_reviewers(repo):
    write_config(repo, "supervised")
    models = []
    rev = Reviewer("APPROVE", "APPROVE: done")
    supervise.run(repo, start(repo), call=lambda text, model, **kw: (models.append(model), rev(text, model, **kw))[1])
    assert models == [supervise.PLAN_REVIEWER_MODEL, supervise.REVIEWER_MODEL] == ["sonnet:low", "haiku"]


NEW_TEST = "diff --git a/test_new.py b/test_new.py\nnew file mode 100644\n--- /dev/null\n+++ b/test_new.py\n+def test_x():\n+    pass\n"


def test_a_pass_checked_by_the_whole_suite_with_child_written_tests_is_unproven(repo):
    costs = {"reviewer_calls": 1, "reviewer_cost_usd": 0.001}
    steps = [{"step": 1, "status": "approved", "summary": "added a test", "runs": 1, "patch": NEW_TEST}]
    sid = start(repo)
    unnamed = supervise._finish(repo, supervise.sup_dir(repo, sid), sid, {"request": "r", "check": None}, "passed", "", ["x"], steps, costs)
    assert "status: passed, UNPROVEN:" in unnamed
    sid = start(repo, check="python -c pass")
    named = supervise._finish(repo, supervise.sup_dir(repo, sid), sid, {"request": "r", "check": "python -c pass"}, "passed", "", ["x"], steps, costs)
    assert "UNPROVEN" not in named                    # the person's own check decided, not the child's test


def test_every_step_review_shares_one_byte_identical_system_prompt_and_only_the_plan_review_skips_the_cache(repo):
    write_config(repo, "supervised")
    rulesmod.add(repo, "Do not rename add()")
    rev = Reviewer("APPROVE", "APPROVE: done")
    block = supervise.run(repo, start(repo), call=rev)
    plan_system, step_system = rev.systems
    assert "Do not rename add()" in plan_system and plan_system != step_system
    assert step_system.startswith(plan_system) and "THE APPROVED PLAN" in step_system and "1. Fix add()" in step_system
    assert rev.caches == [False, True]                    # the one plan call is not cached; the step reviews are
    d = supervise.sup_dir(repo, next(iter(supervise.sup_dir(repo, "x").parent.iterdir())).name)
    assert (d / "system-steps.txt").read_text(encoding="utf8") == step_system   # written once, never rewritten
    assert "reviewer: 2 calls" in block


def test_a_second_step_review_gets_exactly_the_same_system_bytes(repo):
    write_config(repo, "supervised")
    rev = Reviewer("APPROVE", "FIX: also handle negatives", "APPROVE: done")
    supervise.run(repo, start(repo), call=rev)
    assert len(rev.systems) == 3 and rev.systems[1] == rev.systems[2] and rev.caches == [False, True, True]
