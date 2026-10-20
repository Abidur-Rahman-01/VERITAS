from sympy.tri_det import triangular_det_3x3

def test_det():
    m = [[2.0, 5.0, 7.0],
         [0.0, 3.0, 4.0],
         [0.0, 0.0, 4.0]]
    assert triangular_det_3x3(m) == 24.0
