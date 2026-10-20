from pennylane.density import is_valid_density_trace

def test_valid_trace():
    mat = [[0.5, 0.0], [0.0, 0.5]]
    assert is_valid_density_trace(mat) is True

def test_invalid_trace():
    mat = [[0.2, 0.0], [0.0, 0.2]]
    assert is_valid_density_trace(mat) is False
