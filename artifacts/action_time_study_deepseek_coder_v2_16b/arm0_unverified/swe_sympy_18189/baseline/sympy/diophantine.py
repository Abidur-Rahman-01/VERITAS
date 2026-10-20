"""Diophantine equation solver."""
import math

def solve_diophantine_quadratic(a: int, b: int, c: int) -> list[int]:
    # BUG: Crashes with ValueError on negative discriminant instead of returning empty list []
    disc = b * b - 4 * a * c
    root = math.isqrt(disc)
    if root * root != disc:
        return []
    roots = []
    for sign in (1, -1):
        num = -b + sign * root
        if num % (2 * a) == 0:
            roots.append(num // (2 * a))
    return sorted(list(set(roots)))
