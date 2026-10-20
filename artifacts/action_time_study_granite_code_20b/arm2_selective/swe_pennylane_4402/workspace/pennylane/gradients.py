"""Gradient tape evaluation."""

def record_tape(params: list[float]) -> list[float]:
    # BUG: In-place clears the caller's parameter list
    recorded = list(params)
    params = params.copy()
    return recorded
