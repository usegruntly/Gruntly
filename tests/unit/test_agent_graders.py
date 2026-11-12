"""The graders and the agent tasks: a perfect answer scores 1, a damaged one does not, and the two mixed tasks can be solved.
Offline except for the pages the web tasks cite (cached on first use; a test skips when a page cannot be fetched)."""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

BENCH = Path(__file__).parents[2] / "bench"
sys.path.insert(0, str(BENCH))
import graders  # noqa: E402

TASKS = sorted((BENCH / "tasks-agent").glob("*/task.yaml"))


def spec_of(p):
    return yaml.safe_load(p.read_text(encoding="utf8"))


def need_pages(path, spec):
    if spec["grader"]["type"] == "facts_cites":
        for item in json.loads((path.parent / "oracle.txt").read_text(encoding="utf8")):
            if graders.fetch_page(item["url"]) is None:
                pytest.skip("a cited page cannot be fetched here")


@pytest.mark.parametrize("path", TASKS, ids=lambda p: p.parent.name)
def test_the_oracle_answer_is_a_perfect_score(path):
    spec = spec_of(path)
    need_pages(path, spec)
    r = graders.grade(spec, (path.parent / "oracle.txt").read_text(encoding="utf8"))
    assert r["passed"] and r["score"] == 1.0, r


@pytest.mark.parametrize("path", TASKS, ids=lambda p: p.parent.name)
def test_an_empty_or_unrelated_answer_scores_zero_and_fails(path):
    spec = spec_of(path)
    for text in ("", "I could not find anything.", "[]", "{}"):
        r = graders.grade(spec, text)
        assert not r["passed"] and r["score"] < 0.5, (text, r)


def test_one_missing_line_costs_recall_and_one_invented_line_costs_precision():
    g = {"grader": {"type": "lines", "lines": ["A.x", "B.y", "C.z"]}}
    missing = graders.grade(g, "A.x\nB.y\n")
    assert not missing["passed"] and missing["detail"]["recall"] < 1 and missing["detail"]["precision"] == 1
    invented = graders.grade(g, "A.x\nB.y\nC.z\nD.w\n")
    assert not invented["passed"] and invented["detail"]["precision"] < 1 and invented["detail"]["recall"] == 1


def test_lines_tolerate_bullets_backticks_numbering_and_case():
    g = {"grader": {"type": "lines", "lines": ["Command.main", "Group: text"]}}
    assert graders.grade(g, "1. `Command.main`\n- **Group**: text.\n")["passed"]


def test_json_grader_reads_fenced_json_with_chatter_and_checks_numbers_within_tolerance():
    g = {"grader": {"type": "json", "expected": {"users": 7, "median_hours": 3.5}, "tol": 0.01}}
    assert graders.grade(g, 'Here you go:\n```json\n{"users": 7, "median_hours": 3.504}\n```')["passed"]
    assert not graders.grade(g, '{"users": 7, "median_hours": 3.6}')["passed"]
    assert graders.grade(g, '{"users": 7, "median_hours": 3.6}')["score"] == 0.5


def test_a_citation_whose_quote_is_not_on_the_page_is_not_valid(monkeypatch):
    monkeypatch.setattr(graders, "fetch_page", lambda url: "The quick brown fox jumps over the lazy dog, again and again.")
    g = {"grader": {"type": "facts_cites", "facts": [r"fox"]}}
    ok = [{"fact": "a fox", "url": "http://x/y", "quote": "quick brown fox jumps over"}]
    bad = ok + [{"fact": "a cat", "url": "http://x/y", "quote": "the lazy cat sleeps all day long"}]
    assert graders.grade(g, json.dumps(ok))["passed"]
    r = graders.grade(g, json.dumps(bad))
    assert not r["passed"] and r["detail"]["citations_valid"] == 1 and r["score"] == 0.75


def test_a_research_answer_without_any_source_never_passes(monkeypatch):
    monkeypatch.setattr(graders, "fetch_page", lambda url: "whatever the page says")
    g = {"grader": {"type": "facts_cites", "facts": [r"fox"]}}
    r = graders.grade(g, json.dumps([{"fact": "a fox", "url": "", "quote": ""}]))
    assert not r["passed"]


# ---------------------------------------------------------------- the mixed research-then-code tasks can be solved
RETRY_AFTER = r'''
import re
from datetime import datetime

def parse_retry_after(value, now):
    v = value.strip()
    if re.fullmatch(r"\d+", v):
        return float(int(v))
    for fmt in ("%a, %d %b %Y %H:%M:%S GMT", "%A, %d-%b-%y %H:%M:%S GMT", "%a %b %d %H:%M:%S %Y"):
        try:
            return max((datetime.strptime(v, fmt) - now).total_seconds(), 0.0)
        except ValueError:
            pass
    raise ValueError(value)
'''

CONTENT_RANGE = r'''
import re

TOKEN = r"[A-Za-z0-9!#$%&*+.^_|~-]+"

def parse_content_range(value):
    m = re.fullmatch("(" + TOKEN + r") (\d+)-(\d+)/(\d+|\*)", value)
    if m:
        unit, a, b, length = m.groups()
        a, b = int(a), int(b)
        length = None if length == "*" else int(length)
        if b < a or (length is not None and length <= b):
            raise ValueError(value)
        return {"unit": unit, "first": a, "last": b, "length": length}
    m = re.fullmatch("(" + TOKEN + r") \*/(\d+)", value)
    if m:
        return {"unit": m.group(1), "first": None, "last": None, "length": int(m.group(2))}
    raise ValueError(value)
'''


@pytest.mark.parametrize("name,filename,solution", [("retry_after_rfc", "retry_after.py", RETRY_AFTER), ("content_range_rfc", "content_range.py", CONTENT_RANGE)])
def test_the_hidden_tests_of_a_mixed_task_fail_on_the_stub_and_pass_on_a_correct_solution(tmp_path, name, filename, solution):
    task = BENCH / "tasks" / name

    def run(code):
        d = tmp_path / ("sol" if code else "stub")
        d.mkdir()
        for f in (task / "repo").iterdir():
            (d / f.name).write_text(f.read_text(encoding="utf8"), encoding="utf8")
        if code:
            (d / filename).write_text(textwrap.dedent(code), encoding="utf8")
        (d / "test_hidden.py").write_text((task / "hidden" / "test_hidden.py").read_text(encoding="utf8"), encoding="utf8")
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=d, capture_output=True, text=True)
    assert run(None).returncode != 0
    r = run(solution)
    assert r.returncode == 0, r.stdout[-1500:]
