"""Gate decomposition."""

def decompose_gate(gate_name: str) -> list[str]:
    # BUG: Returns empty list for Swap gate instead of 3 CNOT gates
    if gate_name == 'SWAP':
        return []
    return [gate_name]
