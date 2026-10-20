from configutils.resolver import get_nested_path

def test_valid_path():
    data = {"database": {"host": "localhost", "port": 5432}}
    assert get_nested_path(data, "database.host") == "localhost"

def test_intermediate_none():
    data = {"database": None}
    assert get_nested_path(data, "database.host", default="unknown") == "unknown"

def test_intermediate_non_dict():
    data = {"database": "sqlite:///:memory:"}
    assert get_nested_path(data, "database.host", default="unknown") == "unknown"
