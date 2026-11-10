"""`agent-run --supervised`: the child plans, a fresh child does each step, a reviewer (stubbed here) judges each one."""
import json

from gruntly import cli, rules as rulesmod, supervise
from tests.e2e.test_do import write_config


def start(repo, request="Make add() in calc.py add.", check=None):
    sid = supervise.new_id()
    supervise._write(supervise.sup_dir(repo, sid), "task.json", {"request": request, "check": check, "model": None})
    return sid


class Reviewer:
    """Scripted replies, recording what the reviewer was shown."""
    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    def __call__(self, text, model):
        self.seen.append(text)
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
