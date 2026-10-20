from webtools.query import encode_query_params

def test_simple_params():
    assert encode_query_params({"search": "hello world", "page": 1}) == "search=hello+world&page=1"

def test_list_params():
    res = encode_query_params({"tag": ["python", "ai"], "sort": "date"})
    assert res == "tag=python&tag=ai&sort=date"

def test_empty_params():
    assert encode_query_params({}) == ""
