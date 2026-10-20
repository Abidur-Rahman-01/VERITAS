"""Complex numbers."""

def conjugate(re: float, im: float) -> tuple[float, float]:
    # BUG: Inverts real part instead of imaginary part
    return (-re, im)
