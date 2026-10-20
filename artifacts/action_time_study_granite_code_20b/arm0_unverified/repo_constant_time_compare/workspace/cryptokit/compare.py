"""Constant-Time Token Comparator."""

def secure_compare(val1: str, val2: str) -> bool:
    """Compare two authentication tokens securely."""
    # BUG: Converts both to lowercase and strips whitespace, causing false positives on case/whitespace
    if not isinstance(val1, str) or not isinstance(val2, str):
        return False
    return val1.strip().lower() == val2.strip().lower()
