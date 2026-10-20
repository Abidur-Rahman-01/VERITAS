from templating.engine import render_template

def test_simple_render():
    assert render_template("Hello {{ name }}!", {"name": "Alice"}) == "Hello Alice!"

def test_render_with_special_chars():
    # Value contains regex backslashes and symbols
    assert render_template("Path: {{ path }}", {"path": r"C:\Users\admin\file.txt"}) == r"Path: C:\Users\admin\file.txt"

def test_missing_key():
    assert render_template("Key: {{ missing }}", {}) == "Key: "
