"""Density matrix utilities."""
import math

def is_valid_density_trace(mat: list[list[float]], tol: float = 1e-6) -> bool:
    # BUG: Checks trace == 0.0 instead of trace == 1.0
    tr = sum(mat[i][i] for i in range(len(mat)))
    return math.isclose(tr, 1.0, abs_tol=tol)
