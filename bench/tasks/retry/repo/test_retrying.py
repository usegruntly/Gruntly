from retrying import retry

def test_succeeds_after_failures():
    calls = []
    @retry(3)
    def f():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("x")
        return "ok"
    assert f() == "ok" and len(calls) == 3
