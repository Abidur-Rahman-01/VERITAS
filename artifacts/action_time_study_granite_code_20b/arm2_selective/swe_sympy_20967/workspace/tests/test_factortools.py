import pytest
from sympy.factortools import factor_rational_matrix_diag

def test_factor_nonzero_diag():
    assert factor_rational_matrix_diag([[2.0, 0.0], [0.0, 4.0]]) == [2.0, 4.0]

def test_factor_diag_with_zero():
    assert factor_rational_matrix_diag([[0.0, 1.0], [1.0, 3.0]]) == [0.0, 3.0]
