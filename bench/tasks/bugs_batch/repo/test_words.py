from words import word_count

def test_basic():
    assert word_count('A b, a') == {'a': 2, 'b': 1}
