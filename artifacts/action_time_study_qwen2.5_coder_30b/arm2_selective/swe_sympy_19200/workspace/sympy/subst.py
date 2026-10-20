"""Expression substitution."""

def substitute(expr: dict, replacements: dict) -> dict:
    # FIX: Copy expr before replacing variables so original dict is never modified
    result = expr.copy()
    for k, v in replacements.items():
        if k in result:
            result[k] = v
    return result
