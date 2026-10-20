"""Quantum Node execution."""

def broadcast_params(params: list) -> list[list[float]]:
    # BUG: Fails to wrap 1D single-circuit parameters in a batch dimension
    if not params:
        return []
    if not all(isinstance(p, list) for p in params):
        return [params]
    return params
