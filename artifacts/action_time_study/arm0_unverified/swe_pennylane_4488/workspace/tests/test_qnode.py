import pytest
from pennylane.qnode import broadcast_params

def test_batched_input():
    assert broadcast_params([[1.0], [2.0]]) == [[1.0], [2.0]]

def test_unbatched_input_wrapped():
    assert broadcast_params([1.0, 2.0]) == [[1.0, 2.0]]
