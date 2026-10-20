"""Polynomial factorization tools."""

def factor_rational_matrix_diag(mat: list[list[float]]) -> list[float]:
    # BUG: Fails on zero elements on diagonal with ZeroDivisionError
    diag = []
    for i in range(len(mat)):
        val = mat[i][i]
        diag.append(1.0 / (1.0 / val))
    return diag
