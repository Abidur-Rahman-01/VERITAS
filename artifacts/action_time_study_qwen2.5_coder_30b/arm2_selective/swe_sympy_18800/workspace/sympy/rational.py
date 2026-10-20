"""Rational number representations."""
import math

def make_rational(num: int, den: int) -> tuple[int, int]:
    if den == 0:
        raise ZeroDivisionError('Denominator cannot be zero')
    g = math.gcd(abs(num), abs(den))
    num //= g
    den //= g
    # Ensure denominator is always positive
    if den < 0:
        num = -num
        den = -den
    return (num, den)
