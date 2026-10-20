"""Rational number representations."""
import math

def make_rational(num: int, den: int) -> tuple[int, int]:
    if den == 0:
        raise ZeroDivisionError('Denominator cannot be zero')
    g = math.gcd(abs(num), abs(den))
    # BUG: Leaves negative sign on denominator instead of normalizing to numerator
    return (num // g if den >= 0 else -num // g, abs(den) // g)
