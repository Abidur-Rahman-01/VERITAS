from sympy.subst import substitute

def test_immutability():
    orig = {'x': 1, 'y': 2}
    res = substitute(orig, {'x': 10})
    assert res == {'x': 10, 'y': 2}
    assert orig == {'x': 1, 'y': 2}
