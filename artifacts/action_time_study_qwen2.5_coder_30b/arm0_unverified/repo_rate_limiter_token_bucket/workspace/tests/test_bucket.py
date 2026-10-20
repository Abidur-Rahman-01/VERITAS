from ratelimit.bucket import TokenBucket

def test_consume():
    b = TokenBucket(2, 1.0)
    assert b.consume(1) is True
    assert b.consume(1) is True
    assert b.consume(1) is False
