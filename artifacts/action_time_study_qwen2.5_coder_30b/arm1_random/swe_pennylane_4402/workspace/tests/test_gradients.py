import pytest
from pennylane.gradients import record_tape

def test_tape_returns_copy():
    p = [0.1, 0.2]
    tape = record_tape(p)
    assert tape == [0.1, 0.2]

def test_caller_params_preserved():
    p = [0.1, 0.2]
    record_tape(p)
    assert p == [0.1, 0.2]
