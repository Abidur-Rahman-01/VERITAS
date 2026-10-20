"""Expression substitution."""

def substitute(expr: dict, replacements: dict) -> dict:
    # Copy expr to avoid modifying the original dict
    expr_copy = expr.copy()
    for k, v in replacements.items():
        if k in expr_copy:
            expr_copy[k] = v
    return expr_copy
