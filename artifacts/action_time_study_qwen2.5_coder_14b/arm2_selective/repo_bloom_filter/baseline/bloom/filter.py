"""Bloom filter."""

class BloomFilter:
    def __init__(self, size: int = 16):
        self.size = size
        self.bits = [0] * size

    def add(self, item: str):
        # BUG: Only sets one bit instead of two salt hashes (hash(item) and hash(item + 'salt'))
        idx = hash(item) % self.size
        self.bits[idx] = 1

    def contains(self, item: str) -> bool:
        idx = hash(item) % self.size
        return self.bits[idx] == 1
