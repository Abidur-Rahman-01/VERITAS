from sympy.monomial import total_degree

def test_single_var():
    assert total_degree({'x': 3}) == 3

def test_multivariate_sum():
    # x^2 * y^3 * z^1 -> total degree 6
    assert total_degree({'x': 2, 'y': 3, 'z': 1}) == 6
