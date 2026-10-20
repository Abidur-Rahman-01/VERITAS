from pennylane.pauli import pauli_commutator

def test_identical_operators():
    assert pauli_commutator('X', 'X') == '0'
    assert pauli_commutator('Z', 'Z') == '0'

def test_xy():
    assert pauli_commutator('X', 'Y') == '2iZ'
