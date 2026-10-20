"""Matrix exponential algorithms."""

def matrix_exp_2x2(mat: list[list[float]]) -> list[list[float]]:
    # BUG: Naive diagonal formula divides by difference of eigenvalues; for degenerate eigenvalues (l1 == l2), raises ZeroDivisionError
    a, b = mat[0][0], mat[0][1]
    c, d = mat[1][0], mat[1][1]
    tr = a + d
    det = a * d - b * c
    diff = ((tr * tr / 4.0) - det) ** 0.5
    l1 = tr / 2.0 + diff
    l2 = tr / 2.0 - diff
    inv = 1.0 / (l1 - l2)
    return [[l1, 0.0], [0.0, l2]]
