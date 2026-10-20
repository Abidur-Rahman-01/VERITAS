from bloom.filter import BloomFilter

def test_two_hash_bits():
    bf = BloomFilter(64)
    bf.add('hello')
    assert sum(bf.bits) == 2
