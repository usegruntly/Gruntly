"""bench/run_matrix.py: the cell file, what counts as paid, the dry run, the cap, and one real run of a fake parent through the whole path
(task copy, parent launch, hidden tests, results store, report). Nothing here starts a model."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from gruntly import parents
from gruntly.parents.base import Detection, ParentCaps, ParentCommand, ParentOutcome

BENCH = Path(__file__).parents[2] / "bench"
spec = importlib.util.spec_from_file_location("run_matrix", BENCH / "run_matrix.py")
rm = importlib.util.module_from_spec(spec)
sys.modules["run_matrix"] = rm
spec.loader.exec_module(rm)


FIX = "import pathlib; pathlib.Path('slug.py').write_text('def slug(s):\\n    return s.strip().lower().replace(\" \", \"-\")\\n')\nprint('fixed')"


class FakeParent:
    name = "fakep"

    def detect(self):
        return Detection(True, "1")

    def command(self, task, mode, model=None, provider=None, structured=False):
        return ParentCommand([sys.executable, "-c", FIX], {}, task, notes=["a limit"])

    def parse(self, stdout, stderr, exit_code):
        from gruntly.usage import Usage
        return ParentOutcome(stdout.strip(), exit_code != 0, usage=Usage(prompt=100, completion=10, requests=2), turns=2)

    def capabilities(self):
        return ParentCaps(modes=("delegating", "working"))

    def cancel(self, proc):
        pass


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(parents, "table", lambda: {"fakep": FakeParent, "aider": __import__("gruntly.parents.aider", fromlist=["x"]).AiderParent})
    monkeypatch.setattr(parents, "get_parent", lambda n: (FakeParent if n == "fakep" else parents.table()[n])())


def _cells(tmp_path, text):
    p = tmp_path / "cells.toml"
    p.write_text(text, encoding="utf8")
    return p


def test_the_cell_file_is_checked_and_defaults_are_filled(tmp_path, fake):
    cells = rm.load_cells(_cells(tmp_path, '[[cell]]\nparent = "fakep"\nchild_model = "m"\n[[cell]]\nname = "b"\nparent = "fakep"\nmode = "working"\n'))
    assert [c["name"] for c in cells] == ["fakep-delegating-1", "b"] and cells[0]["child_harness"] == "opencode" and cells[0]["mode"] == "delegating"
    for text, why in (('[[cell]]\nparent = "nope"\n', "unknown parent 'nope'"), ('[[cell]]\nparent = "fakep"\nmode = "lean"\n', "mode must be"),
                      ('[[cell]]\nparent = "fakep"\ncolor = "red"\n', "unknown field"), ('[[cell]]\nparent = "fakep"\nchild_provider = "nowhere"\n', "unknown child_provider"),
                      ('[[cell]]\nname = "x"\nparent = "fakep"\n[[cell]]\nname = "x"\nparent = "fakep"\n', "unique"), ('', r"no \[\[cell\]\]"),
                      ('[[cell]]\nparent = "aider"\nmode = "delegating"\n', "cannot run in delegating mode")):
        with pytest.raises(SystemExit, match=why):
            rm.load_cells(_cells(tmp_path, text))


def test_a_cell_may_cost_money_when_a_login_a_hosted_provider_or_a_claude_child_is_involved(tmp_path, fake):
    def why(text):
        return rm.paid_reasons(rm.load_cells(_cells(tmp_path, text))[0])
    assert why('[[cell]]\nparent = "fakep"\n')                                                       # no parent provider: your own login
    assert any("gemini" in w and "free tier" in w for w in why('[[cell]]\nparent = "fakep"\nparent_provider = "gemini"\nchild_provider = "local"\n'))   # a free tier is no guarantee
    assert not why('[[cell]]\nparent = "fakep"\nparent_provider = "ollama"\n')                      # local
    assert any("openai" in w for w in why('[[cell]]\nparent = "fakep"\nparent_provider = "openai"\n'))
    assert any("Claude" in w for w in why('[[cell]]\nparent = "fakep"\nparent_provider = "ollama"\nchild_harness = "claude"\n'))
    assert not why('[[cell]]\nparent = "fakep"\nparent_provider = "ollama"\nmode = "working"\nchild_harness = "claude"\n')    # a working cell has no child


def test_the_example_cells_load_and_the_plan_multiplies_cells_tasks_and_reps():
    cells = rm.load_cells(BENCH / "cells.example.toml")
    assert len(cells) == 5 and len(rm.plan(cells, ["a", "b"], 3)) == 30
    assert [bool(rm.paid_reasons(c)) for c in cells] == [True, True, True, True, False]


def test_a_dry_run_starts_nothing_and_a_paid_run_needs_a_stated_cap(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rm, "run_one", lambda *a, **k: pytest.fail("a dry run must not run anything"))
    monkeypatch.setattr(sys, "argv", ["run_matrix", "--cells", str(BENCH / "cells.example.toml"), "--tasks", "slugify", "--out", str(tmp_path / "o")])
    assert rm.main() == 0
    out = capsys.readouterr().out
    assert "5 cell(s) x 1 task(s) x 1 rep(s) = 5 run(s)" in out and "PAID: the claude parent runs on your own login" in out and "Dry run: nothing was started" in out
    monkeypatch.setattr(sys, "argv", ["run_matrix", "--cells", str(BENCH / "cells.example.toml"), "--tasks", "slugify", "--run"])
    with pytest.raises(SystemExit, match="--yes-paid and --max-usd"):
        rm.main()


def test_the_cap_stops_the_run_before_the_next_one_and_the_report_says_when_a_price_is_unknown(tmp_path, monkeypatch, capsys):
    calls = []

    def fake_run(task_dir, cell, rep, out, **k):
        calls.append(rep)
        return {"cell": cell["name"], "task": task_dir.name, "rep": rep, "passed": True, "wall_s": 5, "parent_usage": {"prompt": 100, "completion": 10},
                "parent_usd": 0.6, "child_usd": 0.0, "usd_total": 0.6, "usd_complete": True}
    monkeypatch.setattr(rm, "run_one", fake_run)
    cells = tmp_path / "c.toml"
    cells.write_text('[[cell]]\nname = "x"\nparent = "claude"\nmode = "working"\n', encoding="utf8")
    out = tmp_path / "o"
    monkeypatch.setattr(sys, "argv", ["run_matrix", "--cells", str(cells), "--tasks", "slugify", "--reps", "5", "--out", str(out), "--run", "--yes-paid", "--max-usd", "1.0"])
    assert rm.main() == 0
    assert calls == [0, 1] and "stopped: the measured dollars ($1.2000) reached the cap $1.00" in capsys.readouterr().out
    assert len((out / "results.jsonl").read_text().splitlines()) == 2 and (out / "report.md").is_file()
    rows = [{"cell": "x", "task": "t", "rep": 0, "passed": True, "wall_s": 4, "parent_usage": None, "parent_usd": None, "child_usd": 0.01, "usd_total": 0.01, "usd_complete": False}]
    assert "lower bound: some prices unknown" in rm.report(rows) and "| unknown |" in rm.report(rows)


def test_a_fake_parent_runs_the_whole_path_task_copy_launch_hidden_tests_and_the_store(tmp_path, monkeypatch, fake, capsys):
    task = tmp_path / "tasks" / "slug"
    (task / "repo").mkdir(parents=True)
    (task / "hidden").mkdir()
    (task / "repo" / "slug.py").write_text("def slug(s):\n    return s\n", encoding="utf8")
    (task / "task.yaml").write_text("brief: Make slug() lowercase, strip, and replace spaces with hyphens.\nallowed_paths: [slug.py]\nacceptance:\n- cmd: python -m pytest -q\n", encoding="utf8")
    (task / "hidden" / "test_hidden.py").write_text("from slug import slug\n\ndef test_it():\n    assert slug(' Hello World ') == 'hello-world'\n", encoding="utf8")
    cell = {"name": "fp", "parent": "fakep", "mode": "delegating", "child_harness": "opencode", "child_model": "m1", "parent_model": "pm"}
    row = rm.run_one(task, cell, 0, tmp_path / "out")
    assert row["passed"] is True and row["cell"] == "fp" and row["parent_turns"] == 2 and row["parent_usage"] == {"prompt": 100, "completion": 10, "cached": 0, "requests": 2}
    assert row["parent_usd"] is None and "unknown" in row["parent_cost_source"] and row["usd_complete"] is False and row["notes"] == ["a limit"]
    assert row["final_patch"]["files"] == 1 and (tmp_path / "out" / "fp.slug.0.final.patch").is_file() and (tmp_path / "out" / "fp.slug.0.parent.out").read_text().startswith("fixed")
    json.dumps(row)
