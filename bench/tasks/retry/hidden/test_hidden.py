import pytest
from retrying import retry

def test_reraises_last_after_all_attempts():
    calls = []
    @retry(2)
    def f():
        calls.append(1)
        raise ValueError(len(calls))
    with pytest.raises(ValueError) as e:
        f()
    assert e.value.args == (2,) and len(calls) == 2

def test_only_listed_exceptions_retry():
    calls = []
    @retry(5, exceptions=(KeyError,))
    def f():
        calls.append(1)
        raise TypeError("no retry")
    with pytest.raises(TypeError):
        f()
    assert len(calls) == 1

def test_passes_args_and_keeps_name():
    @retry(2)
    def add(a, b=1):
        return a + b
    assert add(2, b=3) == 5 and add.__name__ == "add"
