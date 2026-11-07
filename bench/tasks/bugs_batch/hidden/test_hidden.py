from chunks import chunk
from intervals import merge_intervals
from limits import clamp
from pager import paginate
from stats import median
from words import word_count
import pytest


def test_edges_0():
    assert paginate(list(range(10)), 4, 3) == [9]
    assert paginate(list(range(10)), 5, 3) == []

def test_more_1():
    assert word_count("It's fine; it's OK.") == {"it's": 2, 'fine': 1, 'ok': 1}
    assert word_count('') == {}

def test_more_2():
    assert merge_intervals([[1, 2], [2, 3]]) == [[1, 3]]
    d = [[1, 4], [2, 5]]
    merge_intervals(d)
    assert d == [[1, 4], [2, 5]]
    assert merge_intervals([]) == []

def test_more_3():
    assert median([3]) == 3
    assert median([5, 1, 3]) == 3
    with pytest.raises(ValueError):
        median([])

def test_more_4():
    assert clamp(5, 0, 10) == 5
    with pytest.raises(ValueError):
        clamp(1, 10, 0)

def test_more_5():
    assert chunk([], 3) == []
    with pytest.raises(ValueError):
        chunk([1], 0)
