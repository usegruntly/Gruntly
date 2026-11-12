import pytest

from content_range import parse_content_range


def test_unknown_length():
    assert parse_content_range("bytes 0-499/*") == {"unit": "bytes", "first": 0, "last": 499, "length": None}


def test_unsatisfied_range():
    assert parse_content_range("bytes */1234") == {"unit": "bytes", "first": None, "last": None, "length": 1234}


def test_last_byte_is_allowed():
    assert parse_content_range("bytes 0-1233/1234")["last"] == 1233


def test_other_range_units_are_allowed():
    assert parse_content_range("items 0-9/100") == {"unit": "items", "first": 0, "last": 9, "length": 100}


@pytest.mark.parametrize("bad", ["bytes 500-499/1234", "bytes 0-1234/1234", "bytes 0-499/300", "bytes */*", "bytes 0-499", "", "0-499/1234"])
def test_invalid(bad):
    with pytest.raises(ValueError):
        parse_content_range(bad)
