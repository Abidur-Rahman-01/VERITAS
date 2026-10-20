"""Expectation value calculation."""

def compute_diag_expval(diag: list[float], probs: list[float]) -> float:
    return sum(d * p for d, p in zip(diag, probs))
