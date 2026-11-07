from roman import to_roman, from_roman

def test_basic():
    assert to_roman(1994) == "MCMXCIV"
    assert from_roman("XIV") == 14
