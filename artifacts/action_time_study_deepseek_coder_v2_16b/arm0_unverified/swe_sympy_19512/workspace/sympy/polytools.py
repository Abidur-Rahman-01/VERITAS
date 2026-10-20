"""Symbolic polynomial tools."""

def poly_compare(val1, val2, precision=1e-10):
    # BUG: Naive strict equality fails when comparing float approximations
    return abs(float(val1) - float(val2)) < precision
