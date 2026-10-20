import pytest
from pennylane.devices import dispatch_adjoint

def test_base_dispatch():
    assert dispatch_adjoint('PauliX') == 'kernel_x'

def test_adjoint_dispatch():
    assert dispatch_adjoint('Adjoint_PauliX') == 'kernel_x_adjoint'
