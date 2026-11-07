import pytest
from durations import parse_duration

def test_units():
    assert parse_duration("2h") == 7200
    assert parse_duration("90m") == 5400

@pytest.mark.parametrize("bad", ["", "h", "12", "5x", "1h 30m", "m5"])
def test_invalid(bad):
    with pytest.raises(ValueError):
        parse_duration(bad)
