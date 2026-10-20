import pytest
from netutils.retry import calculate_backoff

def test_initial_attempts():
    assert calculate_backoff(0) == 1.0
    assert calculate_backoff(1) == 2.0
    assert calculate_backoff(2) == 4.0

def test_max_delay_cap():
    # 1.0 * (2.0 ** 10) = 1024, should be capped at 30.0
    assert calculate_backoff(10, max_delay=30.0) == 30.0

def test_negative_attempt_raises():
    with pytest.raises(ValueError):
        calculate_backoff(-1)
