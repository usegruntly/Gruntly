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
