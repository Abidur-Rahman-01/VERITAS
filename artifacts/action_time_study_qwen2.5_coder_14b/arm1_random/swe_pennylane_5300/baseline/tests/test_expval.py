from pennylane.expval import compute_diag_expval

def test_diag_expval():
    # Eigenvalues: [1.0, -1.0], Probs: [0.7, 0.3] -> 1*0.7 + (-1)*0.3 = 0.4
    assert round(compute_diag_expval([1.0, -1.0], [0.7, 0.3]), 2) == 0.4
