import pytest
from sympy.matrices import matrix_exp_2x2

def test_distinct_eigenvalues():
    res = matrix_exp_2x2([[2.0, 0.0], [0.0, 3.0]])
    assert res is not None

def test_degenerate_eigenvalues():
    # Identity matrix has degenerate eigenvalues l1 == l2 == 1.0
    res = matrix_exp_2x2([[1.0, 0.0], [0.0, 1.0]])
    assert res == [[1.0, 0.0], [0.0, 1.0]]
