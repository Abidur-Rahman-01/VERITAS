"""Token bucket."""

class TokenBucket:
    def __init__(self, capacity: int, fill_rate: float):
        self.capacity = capacity
        self.fill_rate = fill_rate
        self.tokens = capacity

    def consume(self, amount: int = 1) -> bool:
        # BUG: Consumes even when tokens < amount
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        else:
            return False
