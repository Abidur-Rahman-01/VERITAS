import pytest
from timekit.duration import parse_iso_duration

def test_days_and_time():
    assert parse_iso_duration("P1DT2H30M") == 86400 + 7200 + 1800

def test_time_only():
    assert parse_iso_duration("PT1H") == 3600
    assert parse_iso_duration("PT45M") == 2700
    assert parse_iso_duration("PT30S") == 30

def test_days_only():
    assert parse_iso_duration("P2D") == 172800

def test_invalid_format():
    with pytest.raises(ValueError):
        parse_iso_duration("1 hour")
