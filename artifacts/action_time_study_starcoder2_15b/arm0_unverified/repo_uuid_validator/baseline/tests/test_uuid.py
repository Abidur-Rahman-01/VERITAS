from idtools.uuid import is_valid_uuid4

def test_valid_v4():
    assert is_valid_uuid4('c9a646d3-9c61-4cc9-bc94-e200c8f5f4e1') is True

def test_invalid_version():
    # Version 1 instead of 4
    assert is_valid_uuid4('c9a646d3-9c61-1cc9-bc94-e200c8f5f4e1') is False
