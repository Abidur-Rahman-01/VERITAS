"""Expectation value calculation."""

def compute_diag_expval(diag: list[float], probs: list[float]) -> float:
    # BUG: Multiplies probability by index instead of eigenvalue
    return sum(i * p for i, p in enumerate(probs))
