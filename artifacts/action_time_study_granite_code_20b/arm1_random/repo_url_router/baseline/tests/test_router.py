from routing.router import match_route

def test_simple_match_with_int_conversion():
    res = match_route("/users/<int:user_id>", "/users/1024")
    assert res == {"user_id": 1024}
    assert isinstance(res["user_id"], int)

def test_slug_match():
    res = match_route("/posts/<slug>", "/posts/hello-world")
    assert res == {"slug": "hello-world"}

def test_exact_path_boundaries():
    assert match_route("/api/v1/status", "/api/v1/status/extra") is None
    assert match_route("/api/v1/status", "/prefix/api/v1/status") is None
