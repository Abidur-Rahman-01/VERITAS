"""Quantum Node execution."""

def broadcast_params(params: list) -> list[list[float]]:
    # BUG: Fails to wrap 1D single-circuit parameters in a batch dimension
    if not params:
        return []
    if len(params) == 1 and not isinstance(params[0], list):
        return [params]
    if len(params) == 1 and not isinstance(params[0], list):
        return [params]
    if len(params) == 1 and not isinstance(params[0], list):
        return [params]
    return params
