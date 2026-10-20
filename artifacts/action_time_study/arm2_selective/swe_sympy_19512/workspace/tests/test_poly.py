from sympy.polytools import poly_compare

def test_exact_integers():
    assert poly_compare(1, 1) is True
    assert poly_compare(1, 2) is False

def test_float_precision():
    assert poly_compare(1.0, 1) is True
    assert poly_compare(1.00000001, 1.0) is True
