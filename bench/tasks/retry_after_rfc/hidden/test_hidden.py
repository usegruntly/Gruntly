from datetime import datetime

import pytest

from retry_after import parse_retry_after

NOW = datetime(1999, 12, 31, 23, 59, 0)


def test_zero_and_spaces():
    assert parse_retry_after("0", NOW) == 0.0
    assert parse_retry_after(" 30 ", NOW) == 30.0


@pytest.mark.parametrize("bad", ["-5", "1.5", "abc", "", "Fri, 31 Dec 1999"])
def test_invalid(bad):
    with pytest.raises(ValueError):
        parse_retry_after(bad, NOW)


def test_obsolete_rfc850():
    assert parse_retry_after("Friday, 31-Dec-99 23:59:59 GMT", NOW) == 59.0


def test_obsolete_asctime():
    assert parse_retry_after("Fri Dec 31 23:59:59 1999", NOW) == 59.0


def test_past_date_is_zero():
    assert parse_retry_after("Thu, 30 Dec 1999 00:00:00 GMT", NOW) == 0.0


def test_rfc850_two_digit_year_in_the_past_century():
    later = datetime(2024, 1, 1)
    assert parse_retry_after("Sunday, 06-Nov-94 08:49:37 GMT", later) == 0.0
