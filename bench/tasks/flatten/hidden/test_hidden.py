from flat import flatten

def test_edges():
    assert flatten([]) == []
    assert flatten([["ab", ["cd"]], "e"]) == ["ab", "cd", "e"]
    assert flatten([[[[1]]], 2, [[], [3]]]) == [1, 2, 3]
