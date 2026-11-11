"""`agent-run --review`: one review outside the parent's session, one automatic send-back on FIX (the reviewer is stubbed)."""
import io
import subprocess
import sys

import pytest

from gruntly import cli, review as reviewmod, rules as rulesmod, supervise
from tests.e2e.test_do import write_config


class Reviewer:
    """Scripted replies; records what it was shown and how it was called."""
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, text, model, timeout_s=300, system_file=None, cache=True):
        self.calls.append({"text": text, "model": model, "system": system_file.read_text(encoding="utf8") if system_file else None,
                           "cache": cache})
        return (self.replies.pop(0) if self.replies else "APPROVE: ok"), 0.0072


def run_review(capsys, monkeypatch, repo, reviewer, *flags, request="fix add() so test_calc passes"):
    monkeypatch.chdir(repo)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    monkeypatch.setattr(supervise, "reviewer_call", reviewer)
    assert cli.main(["agent-run", *flags, request]) == 0
    return capsys.readouterr().out.strip()


@pytest.fixture
def proj(repo):
    write_config(repo, "twice")
    return repo


def test_an_approving_review_is_one_line_with_its_cost_and_no_second_run(proj, capsys, monkeypatch):
    rev = Reviewer("APPROVE: add() now returns a + b")
    out = run_review(capsys, monkeypatch, proj, rev, "--review")
    assert "status: passed" in out
    assert "review (sonnet:low, $0.0072, outside your session): APPROVE: add() now returns a + b" in out
    assert "next: nothing to open or rerun; the review approved it" in out
    assert len(rev.calls) == 1 and rev.calls[0]["model"] == "sonnet:low" and rev.calls[0]["cache"] is False
    assert "return a + b" in rev.calls[0]["text"]                       # it was shown the diff
    assert "fix add() so test_calc passes" in rev.calls[0]["system"]    # and the request, in the byte-stable system prompt


def test_a_fix_goes_back_to_the_child_once_in_the_same_call_and_is_reviewed_again(proj, capsys, monkeypatch):
    rulesmod.add(proj, "Do not rename add()")
    rev = Reviewer("FIX: add a docstring to add()", "APPROVE: docstring added")
    out = run_review(capsys, monkeypatch, proj, rev, "--review", "--reviewer", "opus:low")
    assert "review (opus:low, $0.0072, outside your session): FIX: add a docstring to add()" in out
    assert "sent back once, in this call: passed" in out
    assert "second review: APPROVE: docstring added" in out and "$0.0144" in out
    assert len(rev.calls) == 2 and rev.calls[0]["system"] == rev.calls[1]["system"]          # byte-identical prefix
    assert "Do not rename add()" in rev.calls[0]["system"]
    assert "add a docstring" in (proj / "calc.py").read_text().lower() or "docstring" in (proj / "calc.py").read_text()


def test_a_fix_that_stands_after_the_second_review_is_reported_not_hidden(proj, capsys, monkeypatch):
    rev = Reviewer("FIX: first problem", "FIX: still missing the second problem")
    out = run_review(capsys, monkeypatch, proj, rev, "--review")
    assert "status: passed" in out                                            # the gates passed: a reviewer cannot undo that
    assert "second review: FIX: still missing the second problem" in out
    assert "next: the review found a gap" in out and "--continue" in out


def test_without_the_flag_no_reviewer_is_called(proj, capsys, monkeypatch):
    rev = Reviewer()
    out = run_review(capsys, monkeypatch, proj, rev)
    assert "status: passed" in out and "review (" not in out and not rev.calls


def test_the_reviewer_call_uses_a_system_file_effort_and_no_cache_when_asked(monkeypatch, tmp_path):
    seen = {}

    def fake_run(argv, **kw):
        seen.update(argv=argv, env=kw.get("env"))
        return subprocess.CompletedProcess(argv, 0, stdout='{"result": "APPROVE", "total_cost_usd": 0.001}', stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    f = tmp_path / "sys.txt"
    f.write_text("system", encoding="utf8")
    assert supervise.reviewer_call("hello", "sonnet:low", system_file=f, cache=False) == ("APPROVE", 0.001)
    a = seen["argv"]
    assert a[a.index("--system-prompt-file") + 1] == str(f) and "--system-prompt" not in a
    assert a[a.index("--effort") + 1] == "low" and a[a.index("--model") + 1] == "sonnet"
    assert seen["env"]["DISABLE_PROMPT_CACHING"] == "1"
    supervise.reviewer_call("hello", "haiku")                                 # the default keeps today's behaviour
    assert "--system-prompt" in seen["argv"] and "DISABLE_PROMPT_CACHING" not in (seen["env"] or {})


def test_the_system_prompt_file_is_content_addressed(repo):
    text = reviewmod.system_text(repo, "do the thing")
    assert reviewmod.system_file(repo, text) == reviewmod.system_file(repo, text)
    assert reviewmod.system_file(repo, text) != reviewmod.system_file(repo, text + " ")
