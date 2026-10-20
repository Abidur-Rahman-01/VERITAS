"""Monomial operations."""

def total_degree(powers: dict[str, int]) -> int:
    if not powers:
        return 0
    return sum(powers.values())
