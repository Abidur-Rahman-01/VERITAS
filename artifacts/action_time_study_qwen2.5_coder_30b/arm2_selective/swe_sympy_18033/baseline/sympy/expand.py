"""Expression expansion engine."""

def expand_nested(expr: dict, depth: int = 0, max_depth: int = 4) -> dict:
    # BUG: Recursion does not increment depth (passes depth instead of depth + 1)
    if depth >= max_depth:
        return {'_truncated': True}
    res = {}
    for k, v in expr.items():
        if isinstance(v, dict):
            res[k] = expand_nested(v, depth=depth, max_depth=max_depth)
        else:
            res[k] = v
    return res
