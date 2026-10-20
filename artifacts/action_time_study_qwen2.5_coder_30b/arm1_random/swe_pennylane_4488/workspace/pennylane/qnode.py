"""Quantum Node execution."""

def broadcast_params(params: list) -> list[list[float]]:
    # BUG: Fails to wrap 1D single-circuit parameters in a batch dimension
    if not params:
        return []
    # If params is 1D (elements are not lists), wrap it in a list to make it 2D
    if params and not isinstance(params[0], (list, tuple)):
        return [params]
    return params
