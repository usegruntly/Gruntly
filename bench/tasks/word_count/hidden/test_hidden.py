from words import word_count

def test_case_and_punctuation():
    assert word_count("Hello, hello! World.") == {"hello": 2, "world": 1}
    assert word_count("it's fine; it's ok") == {"it's": 2, "fine": 1, "ok": 1}
    assert word_count("") == {}
