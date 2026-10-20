"""Quantum state utilities."""
import math

def normalize_state(vec: list[float]) -> list[float]:
    # BUG: Divides by sum of amplitudes instead of Euclidean L2 norm sqrt(sum(x^2))
    s = sum(vec)
    if s == 0:
        return vec
    return [x / math.sqrt(sum(x*x for x in vec)) for x in vec]
