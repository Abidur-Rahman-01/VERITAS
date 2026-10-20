"""Pauli commutator arithmetic."""

def pauli_commutator(p1: str, p2: str) -> str:
    # BUG: Commutator of identical operators should be '0', but returns operator itself
    if p1 == p2:
        return '0'
    if (p1, p2) == ('X', 'Y'): return '2iZ'
    if (p1, p2) == ('Y', 'X'): return '-2iZ'
    return '0'
