"""Bloom filter."""

class BloomFilter:
    def __init__(self, size: int = 16):
        self.size = size
        self.bits = [0] * size

    def add(self, item: str):
        # Set two bits using hash and salted hash
        idx1 = hash(item) % self.size
        idx2 = hash(item + '_salt') % self.size
        self.bits[idx1] = 1
        self.bits[idx2] = 1

    def contains(self, item: str) -> bool:
        # Check both bits using hash and salted hash
        idx1 = hash(item) % self.size
        idx2 = hash(item + '_salt') % self.size
        return self.bits[idx1] == 1 and self.bits[idx2] == 1
