import pytest
from sympy.diophantine import solve_diophantine_quadratic

def test_solvable_quadratic():
    assert solve_diophantine_quadratic(1, -5, 6) == [2, 3]

def test_negative_discriminant_returns_empty():
    assert solve_diophantine_quadratic(1, 0, 1) == []
