"""Polynomial factorization tools."""

def factor_rational_matrix_diag(mat: list[list[float]]) -> list[float]:
    diag = []
    for i in range(len(mat)):
        val = mat[i][i]
        if val == 0.0:
            diag.append(0.0)
        else:
            diag.append(1.0 / (1.0 / val))
    return diag
