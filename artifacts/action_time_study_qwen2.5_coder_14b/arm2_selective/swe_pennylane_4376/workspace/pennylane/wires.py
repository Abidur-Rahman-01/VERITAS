"""Quantum wire allocation."""

def allocate_wires(wire_names: list[str], n_qubits: int) -> list[str]:
    # BUG: Raises ValueError when len(wire_names) < n_qubits instead of generating aux wires
    if len(wire_names) < n_qubits:
        needed = n_qubits - len(wire_names)
        wire_names.extend([f'aux_{i}' for i in range(1, needed + 1)])
    return wire_names[:n_qubits]
