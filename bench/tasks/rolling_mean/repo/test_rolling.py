from rolling import rolling_mean

def test_basic():
    assert rolling_mean([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]
