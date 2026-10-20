from textmetric.levenshtein import levenshtein

def test_identical():
    assert levenshtein('cat', 'cat') == 0

def test_single_substitution():
    assert levenshtein('cat', 'bat') == 1
