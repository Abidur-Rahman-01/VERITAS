from sympy.rational import make_rational

def test_positive_denom():
    assert make_rational(4, 6) == (2, 3)

def test_negative_denom():
    assert make_rational(1, -2) == (-1, 2)
    assert make_rational(-1, -2) == (1, 2)
