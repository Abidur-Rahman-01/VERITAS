import pytest
from pennylane.wires import allocate_wires

def test_exact_wires():
    assert allocate_wires(['q0', 'q1'], 2) == ['q0', 'q1']

def test_aux_wire_generation():
    assert allocate_wires(['q0'], 3) == ['q0', 'aux_1', 'aux_2']
