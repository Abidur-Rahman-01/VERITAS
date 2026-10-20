"""Gate decomposition."""

def decompose_gate(gate_name: str) -> list[str]:
    # BUG: Returns empty list for Swap gate instead of 3 CNOT gates
    if gate_name == 'SWAP':
        return ['CNOT', 'CNOT', 'CNOT']
    return [gate_name]
