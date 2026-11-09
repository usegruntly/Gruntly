import json

from gruntly import cli, progress


def oc(tool, inp, status="completed"):
    return json.dumps({"type": "tool_use", "part": {"type": "tool", "tool": tool, "state": {"status": status, "input": inp}}})


def test_tool_lines_become_short_labels_never_contents():
    ev = progress.events_from_line(oc("edit", {"filePath": r"C:\proj\src\app.py", "oldString": "SECRET-BODY", "newString": "x"}))
    assert ev == [{"k": "tool", "tool": "edit", "kind": "edit", "what": "proj/src/app.py", "ok": True}]
    run = progress.events_from_line(oc("bash", {"command": "python   fix.py\n --flag"}, "error"))[0]
    assert run["kind"] == "run" and run["what"] == "python fix.py --flag" and run["ok"] is False


def test_the_childs_words_and_steps_are_kept_short():
    say = progress.events_from_line(json.dumps({"type": "text", "part": {"text": "I will   fix\nthe file. " * 30}}))[0]
    assert say["k"] == "say" and len(say["text"]) <= progress.SAY_CHARS and "\n" not in say["text"]
    step = progress.events_from_line(json.dumps({"type": "step_finish", "part": {"tokens": {"input": 11429, "output": 91}}}))[0]
    assert step == {"k": "step", "tokens_in": 11429, "tokens_out": 91}
    assert progress.events_from_line("not json") == []


def test_secrets_in_labels_are_redacted():
    ev = progress.clean({"k": "tool", "what": "curl -H 'Authorization: Bearer sk-abcdefghijklmnopqrstuvwxyz123456' x"})
    assert "abcdefghijklmnopqrstuvwxyz" not in ev["what"]


def test_read_from_returns_only_whole_new_lines(tmp_path):
    p = tmp_path / "progress.jsonl"
    feed = progress.Feed(p)
    feed.emit("gruntly", "start", model="m")
    rows, off = progress.read_from(p)
    assert [r["k"] for r in rows] == ["start"]
    with p.open("a", encoding="utf8") as f:
        f.write('{"t": 1, "who": "child", "k": "to')           # half a line: not returned yet
    assert progress.read_from(p, off) == ([], off)
    with p.open("a", encoding="utf8") as f:
        f.write('ol"}\n')
    assert [r["k"] for r in progress.read_from(p, off)[0]] == ["tool"]


def test_format_names_the_actor():
    assert "child" in progress.format_row({"t": 0, "who": "child", "k": "tool", "kind": "edit", "what": "a.py", "ok": True})
    assert "gruntly" in progress.format_row({"t": 0, "who": "gruntly", "k": "gates", "ok": False, "detail": "acceptance failed"})
    assert "waiting 12s" in progress.format_row({"t": 0, "who": "gruntly", "k": "wait", "secs": 12, "why": "provider rate limit"})


def test_a_run_writes_a_feed_and_watch_prints_it(repo, run_task, make_spec, capsys, monkeypatch):
    res, root = run_task(make_spec("pass", apply_on_pass=True))
    rows, _ = progress.read_from(root / ".gruntly" / "runs" / res["run_id"] / progress.NAME)
    kinds = [r["k"] for r in rows]
    assert kinds[0] == "start" and "attempt" in kinds and "gates" in kinds and kinds[-1] == "done"
    assert rows[-1]["status"] == "passed"
    monkeypatch.chdir(repo)
    assert cli.main(["watch", "--no-follow"]) == 0
    out = capsys.readouterr().out
    assert "finished: passed" in out and "gruntly" in out
