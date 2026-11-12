from content_range import parse_content_range


def test_simple_range():
    assert parse_content_range("bytes 0-499/1234") == {"unit": "bytes", "first": 0, "last": 499, "length": 1234}
