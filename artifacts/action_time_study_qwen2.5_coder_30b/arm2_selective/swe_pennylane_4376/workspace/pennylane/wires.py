"""Quantum wire allocation."""

def allocate_wires(wire_names: list[str], n_qubits: int) -> list[str]:
    # Generate auxiliary wire names if needed
    if len(wire_names) < n_qubits:
        needed = n_qubits - len(wire_names)
        aux_wires = [f'aux_{i}' for i in range(1, needed + 1)]
        wire_names = wire_names + aux_wires
    return wire_names[:n_qubits]
