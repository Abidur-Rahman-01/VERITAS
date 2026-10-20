from cachelib.lru import LRUCache

def test_lru_eviction():
    c = LRUCache(2)
    c.put(1, "one")
    c.put(2, "two")
    assert c.get(1) == "one" # access 1, making 2 the oldest
    c.put(3, "three")        # should evict 2
    assert c.get(2) is None
    assert c.get(1) == "one"
    assert c.get(3) == "three"
