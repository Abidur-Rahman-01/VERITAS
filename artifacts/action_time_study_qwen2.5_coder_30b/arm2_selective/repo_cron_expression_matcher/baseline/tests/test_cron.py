from cronkit.cron import matches_minute

def test_star():
    assert matches_minute('*', 14) is True

def test_step():
    assert matches_minute('*/15', 30) is True
    assert matches_minute('*/15', 31) is False
