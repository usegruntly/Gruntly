from intervals import merge_intervals

def test_basic():
    assert merge_intervals([[2, 6], [1, 3]]) == [[1, 6]]
