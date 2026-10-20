"""Symbolic polynomial tools."""

def poly_compare(val1, val2, precision=1e-7):
    # Handle mixed float and int symbolic comparison accurately
    try:
        return abs(float(val1) - float(val2)) < precision
    except (ValueError, TypeError):
        # Fallback to exact equality for non-numeric values
        return val1 == val2
