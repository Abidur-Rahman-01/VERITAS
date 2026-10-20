"""Expression substitution."""

def substitute(expr: dict, replacements: dict) -> dict:
    # BUG: Mutates expr in place instead of returning a new dict
    for k, v in replacements.items():
        if k in expr:
            expr[k] = v
    return expr
