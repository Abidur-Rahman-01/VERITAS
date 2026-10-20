"""Quantum state utilities."""
import math

def normalize_state(vec: list[float]) -> list[float]:
    # Normalize by L2 Euclidean norm sqrt(sum(x^2))
    s = math.sqrt(sum(x * x for x in vec))
    if s == 0:
        return vec
    return [x / s for x in vec]
