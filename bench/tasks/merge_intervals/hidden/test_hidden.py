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
