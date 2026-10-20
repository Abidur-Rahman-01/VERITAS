"""Monomial operations."""

def total_degree(powers: dict[str, int]) -> int:
    # BUG: Returns max power instead of sum of powers
    if not powers:
        return 0
    return max(powers.values())
