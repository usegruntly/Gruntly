from durations import parse_duration

def test_basic():
    assert parse_duration("1h30m15s") == 5415
    assert parse_duration("45s") == 45
