from limits import clamp

def test_basic():
    assert clamp(15, 0, 10) == 10
    assert clamp(-5, 0, 10) == 0
