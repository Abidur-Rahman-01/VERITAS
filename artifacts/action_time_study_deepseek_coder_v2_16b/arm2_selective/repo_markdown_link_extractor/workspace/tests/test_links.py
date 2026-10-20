from mdtools.links import extract_links

def test_extract_simple_link():
    text = "Check out [Google](https://google.com) for searching."
    assert extract_links(text) == [("Google", "https://google.com")]

def test_ignore_image_tags():
    text = "Here is an image ![logo](https://example.com/logo.png) and a link [docs](https://docs.org)."
    assert extract_links(text) == [("docs", "https://docs.org")]

def test_multiple_links():
    text = "[one](http://1) and [two](http://2)"
    assert extract_links(text) == [("one", "http://1"), ("two", "http://2")]
