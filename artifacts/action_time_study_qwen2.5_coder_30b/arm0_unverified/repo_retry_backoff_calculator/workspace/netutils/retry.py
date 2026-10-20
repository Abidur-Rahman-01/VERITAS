"""Retry Backoff Calculator."""

def calculate_backoff(attempt: int, base_delay: float = 1.0, factor: float = 2.0, max_delay: float = 30.0) -> float:
    """Calculate exponential backoff delay."""
    if attempt < 0:
        raise ValueError("Attempt must be non-negative")
    delay = base_delay * (factor ** attempt)
    return min(delay, max_delay)
