"""Symbolic polynomial tools."""

def poly_compare(val1, val2, precision=1e-7):
    # BUG: Naive strict equality fails when comparing float approximations
    return val1 == val2
