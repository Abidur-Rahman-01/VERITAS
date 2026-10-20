from pennylane.decomp import decompose_gate

def test_swap_decomp():
    assert decompose_gate('SWAP') == ['CNOT', 'CNOT', 'CNOT']

def test_single():
    assert decompose_gate('H') == ['H']
