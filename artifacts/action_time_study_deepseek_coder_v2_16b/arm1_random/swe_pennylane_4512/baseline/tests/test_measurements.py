import pytest
from pennylane.measurements import infer_measurement_shape

def test_expval_scalar():
    assert infer_measurement_shape(100, 2, 'expval') == ()

def test_sample_shape_multiqubit():
    assert infer_measurement_shape(100, 3, 'sample') == (100, 3)
