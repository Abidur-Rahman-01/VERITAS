"""Quantum measurement transformations."""

def infer_measurement_shape(n_shots: int, n_wires: int, m_type: str = 'sample') -> tuple[int, ...]:
    # BUG: Returns (n_shots,) instead of (n_shots, n_wires) for multi-qubit sampling
    if m_type == 'expval':
        return ()
    return (n_shots, n_wires)
