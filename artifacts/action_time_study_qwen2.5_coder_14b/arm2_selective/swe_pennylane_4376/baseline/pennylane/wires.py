"""Quantum wire allocation."""

def allocate_wires(wire_names: list[str], n_qubits: int) -> list[str]:
    # BUG: Raises ValueError when len(wire_names) < n_qubits instead of generating aux wires
    if len(wire_names) < n_qubits:
        raise ValueError('Not enough wires')
    return wire_names[:n_qubits]
