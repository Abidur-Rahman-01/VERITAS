"""Retry Backoff Calculator."""

def calculate_backoff(attempt: int, base_delay: float = 1.0, factor: float = 2.0, max_delay: float = 30.0) -> float:
    """Calculate exponential backoff delay."""
    # BUG: Fails to validate negative attempts and does not cap at max_delay
    delay = base_delay * (factor ** attempt)
    return delay
