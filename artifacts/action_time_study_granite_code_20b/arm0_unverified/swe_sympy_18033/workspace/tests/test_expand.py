import pytest
from sympy.expand import expand_nested

def test_flat_dict():
    assert expand_nested({'a': 1}) == {'a': 1}

def test_deeply_nested_bounded():
    nested = {'x': {'x': {'x': {'x': {'x': 1}}}}}
    res = expand_nested(nested, depth=0, max_depth=3)
    assert res['x']['x']['x'] == {'_truncated': True}
