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
