"""Triangular matrix determinant."""

def triangular_det_3x3(mat: list[list[float]]) -> float:
    # Compute product of diagonal elements
    return mat[0][0] * mat[1][1] * mat[2][2]
