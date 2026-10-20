import math
from pennylane.state import normalize_state

def test_l2_norm():
    vec = [3.0, 4.0]
    res = normalize_state(vec)
    assert math.isclose(res[0], 0.6)
    assert math.isclose(res[1], 0.8)
