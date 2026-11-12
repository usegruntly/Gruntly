from datetime import datetime

from retry_after import parse_retry_after

NOW = datetime(1999, 12, 31, 23, 59, 0)


def test_delay_seconds():
    assert parse_retry_after("120", NOW) == 120.0


def test_http_date():
    assert parse_retry_after("Fri, 31 Dec 1999 23:59:59 GMT", NOW) == 59.0
