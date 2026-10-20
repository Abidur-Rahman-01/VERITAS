"""LRU Cache."""
from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = OrderedDict()

    def get(self, key):
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key, value):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        # BUG: popitem(last=True) removes the MOST recently added item instead of the LEAST recently used
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)
