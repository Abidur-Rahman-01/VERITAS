from clitools.parser import ArgumentParser

def test_parse_defaults():
    p = ArgumentParser()
    p.add_argument("port", default=8080, required=False)
    p.add_argument("host", default="localhost", required=False)
    res = p.parse(["--port", "9000"])
    assert res["port"] == "9000"
    assert res["host"] == "localhost"

def test_parse_missing_required():
    p = ArgumentParser()
    p.add_argument("config", required=True)
    try:
        p.parse([])
        assert False, "Should raise ValueError"
    except ValueError:
        pass
