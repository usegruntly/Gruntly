from flat import flatten

def test_basic():
    assert flatten([1, [2, [3]]]) == [1, 2, 3]
