"""Gradient tape evaluation."""

def record_tape(params: list[float]) -> list[float]:
    # FIXED: Return a copy without mutating the caller's list
    return list(params)
