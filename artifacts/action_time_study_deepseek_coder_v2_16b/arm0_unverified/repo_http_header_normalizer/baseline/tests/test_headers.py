from httpkit.headers import normalize_headers

def test_basic_headers():
    raw = [("Host", " example.com "), ("Content-Type", "text/html")]
    assert normalize_headers(raw) == {"host": "example.com", "content-type": "text/html"}

def test_duplicate_headers():
    raw = [("Accept", "text/html"), ("accept", "application/json"), ("ACCEPT", "image/webp")]
    assert normalize_headers(raw) == {"accept": "text/html, application/json, image/webp"}
