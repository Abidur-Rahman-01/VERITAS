"""Bloom filter."""

class BloomFilter:
    def __init__(self, size: int = 16):
        self.size = size
        self.bits = [0] * size

    def add(self, item: str):
        # BUG: Only sets one bit instead of two salt hashes (hash(item) and hash(item + 'salt'))
        idx1 = hash(item) % self.size
        idx2 = hash(item + '_salt') % self.size
        self.bits[idx1] = 1
        self.bits[idx2] = 1

    def contains(self, item: str) -> bool:
        idx1 = hash(item) % self.size
        idx2 = hash(item + '_salt') % self.size
        return self.bits[idx1] == 1 and self.bits[idx2] == 1
