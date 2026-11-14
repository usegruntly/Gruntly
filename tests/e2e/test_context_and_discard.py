"""Two things the website session ran into (2026-11-13): a file named in a request only as a SOURCE was a file the child had to change, and a
discarded run took its record, and so the evidence of how it went, with it."""
import io
import json
import sys

from gruntly import agent, cli
from tests.conftest import sh
from tests.e2e.test_do import write_config

REQUEST = 'In "my page.html" replace [placeholder] with the text of "source.txt". Change nothing else.'


def site(repo):
    web = repo / "site"
    web.mkdir()
    (web / "my page.html").write_text("<p>[placeholder]</p>\n")
    (web / "source.txt").write_text("hello\n")
    (repo / "calc.py").unlink()
    (repo / "test_calc.py").unlink()
    sh(repo, "git", "add", "-A")
    sh(repo, "git", "commit", "-qm", "site only")
    return web


def say(capsys, monkeypatch, repo, request, *flags):
    monkeypatch.chdir(repo)
    monkeypatch.setattr("sys.stdin", io.StringIO(request))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    assert cli.main(["agent-run", *flags]) == 0
    return capsys.readouterr().out.strip()


def test_without_context_every_file_the_request_names_has_to_change(repo, capsys, monkeypatch):
    site(repo)
    write_config(repo, "edit_page")                                                     # edits the page only
    out = say(capsys, monkeypatch, repo, REQUEST)
    assert "status: passed" not in out and "source.txt" in out                           # the source was named, so it "must change"


def test_a_context_file_is_read_only_and_does_not_have_to_change(repo, capsys, monkeypatch):
    web = site(repo)
    write_config(repo, "edit_page")
    out = say(capsys, monkeypatch, repo, REQUEST, "--context", "site/source.txt")
    assert "status: passed" in out, out
    assert "hello" in (web / "my page.html").read_text() and (web / "source.txt").read_text() == "hello\n"


def test_the_plan_marks_the_context_file_as_context_and_forbids_changing_it(repo):
    site(repo)
    plan, raw = agent.text_plan(REQUEST, repo, ["site/source.txt"])
    agent.apply_context(raw, ["site/source.txt"])
    assert raw["allowed_paths"] == ["site/my page.html"]
    assert raw["context_files"] == ["site/source.txt"] and raw["deny_paths"] == ["site/source.txt"]
    assert "source.txt" not in raw["acceptance"][0]["cmd"] and "my page.html" in raw["acceptance"][0]["cmd"]


def test_context_paths_keeps_only_the_files_inside_the_project(repo, tmp_path, monkeypatch):
    import argparse
    monkeypatch.chdir(repo)
    a = argparse.Namespace(context=[str(tmp_path / "elsewhere.txt"), "site/source.txt"])
    assert cli._context_paths(a, repo) == ["site/source.txt"]


# A --context file outside the project used to be dropped without a word: the child works in a copy of the project and could not open it, so
# it answered "the file is missing from my worktree" (two failed runs in the website session, 2026-11-14). Now its text travels in the brief.
def test_a_context_file_outside_the_project_travels_as_text(repo, tmp_path, monkeypatch):
    import argparse
    monkeypatch.chdir(repo)
    snippet = tmp_path / "snippet.txt"
    snippet.write_text("    line one\n    line two\n", encoding="utf8")
    a = argparse.Namespace(context=[str(snippet), "site/source.txt"])
    assert cli._context_outside(a, repo) == [("snippet.txt", "    line one\n    line two\n")]
    raw = {"brief": "do the thing", "allowed_paths": ["a.html"], "context_files": []}
    agent.apply_context(raw, ["site/source.txt"], cli._context_outside(a, repo))
    assert "    line one\n    line two" in raw["brief"] and "--- snippet.txt ---" in raw["brief"] and "NOT files in the project" in raw["brief"]
    assert raw["context_files"] == ["site/source.txt"]                      # the one inside the project is still just read


def test_a_context_file_outside_the_project_that_cannot_be_used_is_an_error_not_a_silent_drop(repo, tmp_path, monkeypatch):
    import argparse

    import pytest
    monkeypatch.chdir(repo)
    with pytest.raises(ValueError, match="does not exist"):
        cli._context_outside(argparse.Namespace(context=[str(tmp_path / "gone.txt")]), repo)
    big = tmp_path / "big.txt"
    big.write_text("x" * (agent.CONTEXT_EMBED_MAX + 1), encoding="utf8")
    with pytest.raises(ValueError, match="cannot open paths outside"):
        cli._context_outside(argparse.Namespace(context=[str(big)]), repo)
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"\xff\xfe\x00\x80")
    with pytest.raises(ValueError, match="not readable text"):
        cli._context_outside(argparse.Namespace(context=[str(blob)]), repo)


def test_a_run_with_an_outside_context_file_puts_its_text_in_the_childs_brief(repo, tmp_path, capsys, monkeypatch):
    web = site(repo)
    write_config(repo, "edit_page")
    snippet = tmp_path / "snippet.txt"
    snippet.write_text("UNIQUE-REFERENCE-TEXT\n", encoding="utf8")
    out = say(capsys, monkeypatch, repo, 'In "my page.html" replace [placeholder] with the reference text. Change nothing else.', "--context", str(snippet))
    assert "status: passed" in out, out
    spec = json.loads(next((repo / ".gruntly" / "runs").glob("r_*/spec.json")).read_text(encoding="utf8"))
    assert "UNIQUE-REFERENCE-TEXT" in spec["brief"] and web.joinpath("source.txt").read_text() == "hello\n"


def test_an_unusable_outside_context_file_stops_the_call_with_a_clear_block(repo, tmp_path, capsys, monkeypatch):
    site(repo)
    write_config(repo, "edit_page")
    out = say(capsys, monkeypatch, repo, REQUEST, "--context", str(tmp_path / "gone.txt"))
    assert "status: error" in out and "does not exist" in out and not (repo / ".gruntly" / "runs").exists()


def test_a_discarded_run_leaves_one_line_of_evidence_behind(run_task, make_spec, capsys, monkeypatch):
    res, root = run_task(make_spec("no_fix", max_attempts=1))
    assert res["status"] != "passed"
    monkeypatch.chdir(root)
    assert cli.main(["discard", res["run_id"]]) == 0
    capsys.readouterr()
    assert not (root / ".gruntly" / "runs" / res["run_id"]).exists()                    # the run itself is gone, as before
    lines = [json.loads(x) for x in (root / ".gruntly" / "discarded.jsonl").read_text(encoding="utf8").splitlines()]
    assert len(lines) == 1
    kept = lines[0]
    assert kept["run_id"] == res["run_id"] and kept["status"] == res["status"] and kept["attempts"] == res["attempts"]
    assert "acceptance" in kept["failed_gates"] and "discarded_at" in kept and "child_cost_usd" in kept and "wall_s" in kept
    run_task_again = run_task(make_spec("no_fix", max_attempts=1))[0]                    # a second discard appends, it does not overwrite
    assert cli.main(["discard", run_task_again["run_id"]]) == 0
    assert len((root / ".gruntly" / "discarded.jsonl").read_text(encoding="utf8").splitlines()) == 2
