from sympy.complex_tools import conjugate

def test_conjugate():
    assert conjugate(3.0, 4.0) == (3.0, -4.0)
    assert conjugate(2.0, -5.0) == (2.0, 5.0)
