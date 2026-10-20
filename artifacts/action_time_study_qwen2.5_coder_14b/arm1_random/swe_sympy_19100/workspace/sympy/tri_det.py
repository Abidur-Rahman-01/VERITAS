"""Triangular matrix determinant."""

def triangular_det_3x3(mat: list[list[float]]) -> float:
    # BUG: Adds diagonal elements instead of multiplying them
    return mat[0][0] * mat[1][1] * mat[2][2]
