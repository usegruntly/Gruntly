"""Generates bench/tasks/<name>/ from the definitions below. Run once; the output is committed.

Each task folder has:
  task.yaml        brief, allowed_paths, acceptance (what the parent and child may see)
  repo/            starter files, including the visible test used as the acceptance command
  hidden/test_hidden.py   judged after the run; neither the parent nor the child ever sees it
"""
from pathlib import Path
from textwrap import dedent

import yaml

T = {}


def task(name, brief, module, stub, visible, hidden):
    T[name] = dict(brief=dedent(brief).strip(), module=module, stub=dedent(stub).lstrip("\n"),
                   visible=dedent(visible).lstrip("\n"), hidden=dedent(hidden).lstrip("\n"))


task("slugify", "Implement slugify(text) in slugify.py: lowercase, replace runs of non-alphanumeric characters with a single hyphen, no leading or trailing hyphens.",
     "slugify", '''
def slugify(text):
    raise NotImplementedError
''', '''
from slugify import slugify

def test_basic():
    assert slugify("Hello World") == "hello-world"
''', '''
from slugify import slugify

def test_runs_and_edges():
    assert slugify("  Hello,   World!!  ") == "hello-world"
    assert slugify("a--b__c") == "a-b-c"
    assert slugify("---") == ""
    assert slugify("Python 3.12") == "python-3-12"
''')

task("paginate", "paginate(items, page, per_page) in pager.py returns the items for a 1-based page but is off by one. Fix it.",
     "pager", '''
def paginate(items, page, per_page):
    start = page * per_page
    return items[start:start + per_page]
''', '''
from pager import paginate

def test_first_page():
    assert paginate(list(range(10)), 1, 3) == [0, 1, 2]
''', '''
from pager import paginate

def test_other_pages():
    data = list(range(10))
    assert paginate(data, 2, 3) == [3, 4, 5]
    assert paginate(data, 4, 3) == [9]
    assert paginate(data, 5, 3) == []
''')

task("parse_duration", "Implement parse_duration(s) in durations.py returning seconds for strings like '1h30m15s', '45s', '2h', '90m'. Raise ValueError for anything else (empty, unknown unit, no digits).",
     "durations", '''
def parse_duration(s):
    raise NotImplementedError
''', '''
from durations import parse_duration

def test_basic():
    assert parse_duration("1h30m15s") == 5415
    assert parse_duration("45s") == 45
''', '''
import pytest
from durations import parse_duration

def test_units():
    assert parse_duration("2h") == 7200
    assert parse_duration("90m") == 5400

@pytest.mark.parametrize("bad", ["", "h", "12", "5x", "1h 30m", "m5"])
def test_invalid(bad):
    with pytest.raises(ValueError):
        parse_duration(bad)
''')

task("lru_cache", "Implement class LRUCache(capacity) in lru.py with get(key) (returns None if missing, marks key recently used) and put(key, value) (evicts the least recently used key when over capacity).",
     "lru", '''
class LRUCache:
    def __init__(self, capacity):
        raise NotImplementedError
''', '''
from lru import LRUCache

def test_basic():
    c = LRUCache(2)
    c.put("a", 1)
    assert c.get("a") == 1
    assert c.get("zzz") is None
''', '''
from lru import LRUCache

def test_eviction_order():
    c = LRUCache(2)
    c.put("a", 1); c.put("b", 2)
    c.get("a")
    c.put("c", 3)
    assert c.get("b") is None and c.get("a") == 1 and c.get("c") == 3

def test_update_refreshes():
    c = LRUCache(2)
    c.put("a", 1); c.put("b", 2); c.put("a", 10); c.put("c", 3)
    assert c.get("a") == 10 and c.get("b") is None
''')

task("word_count", "word_count(text) in words.py should count words case-insensitively and ignore punctuation, returning a dict word -> count. It currently splits on whitespace only. Fix it.",
     "words", '''
def word_count(text):
    counts = {}
    for w in text.split():
        counts[w] = counts.get(w, 0) + 1
    return counts
''', '''
from words import word_count

def test_basic():
    assert word_count("A b, a") == {"a": 2, "b": 1}
''', '''
from words import word_count

def test_case_and_punctuation():
    assert word_count("Hello, hello! World.") == {"hello": 2, "world": 1}
    assert word_count("it's fine; it's ok") == {"it's": 2, "fine": 1, "ok": 1}
    assert word_count("") == {}
''')

task("flatten", "Implement flatten(x) in flat.py: flatten arbitrarily nested lists into one flat list, preserving order. Strings are not lists and must stay whole.",
     "flat", '''
def flatten(x):
    raise NotImplementedError
''', '''
from flat import flatten

def test_basic():
    assert flatten([1, [2, [3]]]) == [1, 2, 3]
''', '''
from flat import flatten

def test_edges():
    assert flatten([]) == []
    assert flatten([["ab", ["cd"]], "e"]) == ["ab", "cd", "e"]
    assert flatten([[[[1]]], 2, [[], [3]]]) == [1, 2, 3]
''')

task("retry", "Implement a decorator retry(times, exceptions=(Exception,)) in retrying.py: call the function up to `times` times, retrying only when one of `exceptions` is raised, and re-raise the last exception if all attempts fail. Return the function's value on success.",
     "retrying", '''
def retry(times, exceptions=(Exception,)):
    raise NotImplementedError
''', '''
from retrying import retry

def test_succeeds_after_failures():
    calls = []
    @retry(3)
    def f():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("x")
        return "ok"
    assert f() == "ok" and len(calls) == 3
''', '''
import pytest
from retrying import retry

def test_reraises_last_after_all_attempts():
    calls = []
    @retry(2)
    def f():
        calls.append(1)
        raise ValueError(len(calls))
    with pytest.raises(ValueError) as e:
        f()
    assert e.value.args == (2,) and len(calls) == 2

def test_only_listed_exceptions_retry():
    calls = []
    @retry(5, exceptions=(KeyError,))
    def f():
        calls.append(1)
        raise TypeError("no retry")
    with pytest.raises(TypeError):
        f()
    assert len(calls) == 1

def test_passes_args_and_keeps_name():
    @retry(2)
    def add(a, b=1):
        return a + b
    assert add(2, b=3) == 5 and add.__name__ == "add"
''')

task("roman", "Implement to_roman(n) (1..3999) and from_roman(s) in roman.py. Raise ValueError for out-of-range numbers and for invalid roman numerals.",
     "roman", '''
def to_roman(n):
    raise NotImplementedError

def from_roman(s):
    raise NotImplementedError
''', '''
from roman import to_roman, from_roman

def test_basic():
    assert to_roman(1994) == "MCMXCIV"
    assert from_roman("XIV") == 14
''', '''
import pytest
from roman import to_roman, from_roman

def test_roundtrip():
    for n in range(1, 4000, 7):
        assert from_roman(to_roman(n)) == n

@pytest.mark.parametrize("n", [0, -1, 4000])
def test_range(n):
    with pytest.raises(ValueError):
        to_roman(n)

@pytest.mark.parametrize("s", ["", "IIII", "VX", "ABC", "IC"])
def test_invalid(s):
    with pytest.raises(ValueError):
        from_roman(s)
''')

task("merge_intervals", "merge_intervals(intervals) in intervals.py should merge overlapping or touching [start, end] pairs and return them sorted. It currently breaks on unsorted input and on touching intervals. Fix it.",
     "intervals", '''
def merge_intervals(intervals):
    out = []
    for s, e in intervals:
        if out and s < out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out
''', '''
from intervals import merge_intervals

def test_basic():
    assert merge_intervals([[2, 6], [1, 3]]) == [[1, 6]]
''', '''
from intervals import merge_intervals

def test_unsorted_and_touching():
    assert merge_intervals([[8, 10], [1, 3], [2, 6]]) == [[1, 6], [8, 10]]
    assert merge_intervals([[1, 2], [2, 3]]) == [[1, 3]]
    assert merge_intervals([]) == []
    assert merge_intervals([[5, 5]]) == [[5, 5]]

def test_does_not_mutate_input():
    data = [[1, 4], [2, 5]]
    merge_intervals(data)
    assert data == [[1, 4], [2, 5]]
''')

task("rolling_mean", "Implement rolling_mean(values, window) in rolling.py returning the mean of each full window (len(values) - window + 1 results, floats). Return [] if the window is larger than the list. Raise ValueError if window < 1.",
     "rolling", '''
def rolling_mean(values, window):
    raise NotImplementedError
''', '''
from rolling import rolling_mean

def test_basic():
    assert rolling_mean([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]
''', '''
import pytest
from rolling import rolling_mean

def test_edges():
    assert rolling_mean([1, 2], 5) == []
    assert rolling_mean([4], 1) == [4.0]
    assert rolling_mean([], 1) == []

@pytest.mark.parametrize("w", [0, -2])
def test_bad_window(w):
    with pytest.raises(ValueError):
        rolling_mean([1, 2, 3], w)
''')


def main():
    root = Path(__file__).parent / "tasks"
    for name, t in T.items():
        d = root / name
        (d / "repo").mkdir(parents=True, exist_ok=True)
        (d / "hidden").mkdir(exist_ok=True)
        (d / "repo" / f"{t['module']}.py").write_text(t["stub"], encoding="utf8", newline="\n")
        (d / "repo" / f"test_{t['module']}.py").write_text(t["visible"], encoding="utf8", newline="\n")
        (d / "hidden" / "test_hidden.py").write_text(t["hidden"], encoding="utf8", newline="\n")
        spec = {"brief": t["brief"], "allowed_paths": [f"{t['module']}.py"],
                "acceptance": [{"cmd": f"python -m pytest -q test_{t['module']}.py"}]}
        (d / "task.yaml").write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf8", newline="\n")
    print(f"wrote {len(T)} tasks")


if __name__ == "__main__":
    main()
