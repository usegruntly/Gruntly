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
    diffs = [r for r in rows if r["k"] == "diff"]
    assert diffs and diffs[-1]["final"] and diffs[-1]["ok"] is True and diffs[-1]["lines"] and diffs[-1]["ins"] >= 1
    assert any(ln.startswith("+") for ln in diffs[-1]["lines"])
    monkeypatch.chdir(repo)
    assert cli.main(["watch", "--no-follow"]) == 0
    out = capsys.readouterr().out
    assert "finished: passed" in out and "gruntly" in out and "changes (attempt 1)" in out


PATCH = """diff --git a/calc.py b/calc.py
index 111..222 100644
--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,2 @@ def add
 def add(a, b):
-    return a - b
+    return a + b
diff --git a/new.txt b/new.txt
new file mode 100644
index 000..333
--- /dev/null
+++ b/new.txt
@@ -0,0 +1 @@
+hello
"""


def test_compact_diff_keeps_headers_changes_and_counts_and_caps_the_length():
    d = progress.compact_diff(PATCH)
    assert d["files"] == 2 and d["ins"] == 2 and d["del"] == 1 and d["more"] == 0
    assert d["lines"][0] == "F calc.py" and "F new.txt (new)" in d["lines"]
    assert "-    return a - b" in d["lines"] and "+    return a + b" in d["lines"]
    assert not any(ln.startswith(("index", "---", "+++")) for ln in d["lines"])
    small = progress.compact_diff(PATCH, limit=3)
    assert len(small["lines"]) == 3 and small["more"] > 0


def test_live_patch_shows_new_and_edited_files_without_touching_the_real_index(tmp_path):
    from gruntly import worktree as wt
    wt.git(["init", "-q", "-b", "main"], tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf8")
    wt.git(["add", "-A"], tmp_path)
    wt.git(["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "i"], tmp_path)
    (tmp_path / "a.py").write_text("x = 2\n", encoding="utf8")
    (tmp_path / "b.py").write_text("y = 1\n", encoding="utf8")
    staged_before = wt.git(["diff", "--cached", "--name-only"], tmp_path).stdout
    out = wt.live_patch(tmp_path, "HEAD")
    assert "-x = 1" in out and "+x = 2" in out and "b.py" in out and "+y = 1" in out
    assert wt.git(["diff", "--cached", "--name-only"], tmp_path).stdout == staged_before == ""
