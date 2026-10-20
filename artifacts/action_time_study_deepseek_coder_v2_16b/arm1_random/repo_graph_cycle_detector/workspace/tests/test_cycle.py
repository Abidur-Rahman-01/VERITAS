from graphs.cycle import has_cycle

def test_dag():
    assert has_cycle({'a': ['b'], 'b': []}) is False

def test_cycle():
    assert has_cycle({'a': ['b'], 'b': ['a']}) is True
