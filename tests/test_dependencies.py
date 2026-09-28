"""Extractor fixtures are software tests, not research benchmark observations."""

import json

import pytest

from veritas.cli import dispatch, parser
from veritas.dependencies import compare_symbols, extract_dependencies, write_dependencies
from veritas.io import file_hash


def source(root, path, text):
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text)


def test_direct_import_alias_relative_and_module_calls(tmp_path):
    source(tmp_path, "pkg/__init__.py", "")
    source(tmp_path, "pkg/api.py", "def f(value):\n    return value\n")
    source(tmp_path, "pkg/use.py", """from .api import f as local
import pkg.api as api
import pkg.api
from . import api as sibling
def caller():
    local(1)
    api.f(2)
    pkg.api.f(3)
    sibling.f(4)
""")
    graph = extract_dependencies(tmp_path)
    assert graph["coverage"]["static_candidates"] == 4
    assert graph["coverage"]["unresolved"] == 0
    assert all(e["prerequisite"] == "pkg/api.py::f@1" for e in graph["edges"])
    assert all(e["consumer"] == "pkg/use.py::caller@5" for e in graph["edges"])
    assert graph == extract_dependencies(tmp_path)


def test_shadowing_dynamic_dispatch_decorators_and_unknowns(tmp_path):
    source(tmp_path, "a.py", """def f():
    pass
@unknown_decorator
def decorated():
    pass
def shadow(f):
    f()
def assign():
    f()
    f = None
class C:
    def method(self):
        self.other()
        f()
def caller():
    decorated()
    getattr(C, 'method')()
""")
    graph = extract_dependencies(tmp_path)
    assert len(graph["edges"]) == 1
    assert "C.method" in graph["edges"][0]["consumer"]
    reasons = {r["reason"] for r in graph["calls"] if r["status"] == "unresolved"}
    assert {"local_binding_or_dynamic_dispatch", "decorated_target",
            "dynamic_call_expression"} <= reasons


def test_nested_and_comprehension_scopes_never_false_resolve(tmp_path):
    source(tmp_path, "a.py", """def f():
    return 1
def outer():
    def inner():
        f()
    inner()
    values = [f() for f in []]
    callback = lambda: f()
""")
    graph = extract_dependencies(tmp_path)
    assert graph["edges"] == []
    assert graph["coverage"]["calls"] == 4
    assert any(s["qualified_name"] == "outer.inner" and s["nested"] for s in graph["symbols"])


@pytest.mark.parametrize("code", [
    "def f(): pass\ndef f(): pass\ndef caller(): f()\n",
    "def f(): pass\nf = None\ndef caller(): f()\n",
    "if True:\n    def f(): pass\ndef caller(): f()\n",
    "from external import *\ndef f(): pass\ndef caller(): f()\n",
])
def test_ambiguous_conditional_and_wildcard_bindings(tmp_path, code):
    source(tmp_path, "a.py", code)
    assert extract_dependencies(tmp_path)["edges"] == []


def test_module_name_collision_not_resolved(tmp_path):
    source(tmp_path, "pkg.py", "def f(): pass\n")
    source(tmp_path, "pkg/__init__.py", "def f(): pass\n")
    source(tmp_path, "use.py", "from pkg import f\ndef caller(): f()\n")
    graph = extract_dependencies(tmp_path)
    assert graph["edges"] == []
    assert graph["calls"][0]["reason"] == "external_or_ambiguous_module"


def test_parse_failure_does_not_hide_module_ambiguity(tmp_path):
    source(tmp_path, "pkg.py", "def broken syntax")
    source(tmp_path, "pkg/__init__.py", "def f(): pass\n")
    source(tmp_path, "use.py", "from pkg import f\ndef caller(): f()\n")
    assert extract_dependencies(tmp_path)["calls"][0]["reason"] == "external_or_ambiguous_module"
    (tmp_path / "pkg/__init__.py").unlink()
    assert extract_dependencies(tmp_path)["calls"][0]["reason"] == "target_module_parse_error"


def test_no_import_execution_parse_errors_and_symlink_boundaries(tmp_path):
    root = tmp_path / "repo"
    marker = tmp_path / "executed"
    source(root, "good.py", f"open({str(marker)!r}, 'w').write('bad')\ndef f(): pass\n")
    source(root, "bad.py", "def syntax error")
    source(root, ".venv/ignored.py", "def ignored(): pass\n")
    outside = tmp_path / "outside"
    source(outside, "secret.py", "SECRET = 1\n")
    (root / "link.py").symlink_to(outside / "secret.py")
    (root / "linked").symlink_to(outside, target_is_directory=True)
    graph = extract_dependencies(root)
    assert not marker.exists()
    assert graph["coverage"]["python_files"] == 2
    assert graph["errors"] == [{"path": "bad.py", "reason": "SyntaxError", "line": 1}]
    assert len(graph["skipped"]) == 3
    assert "SECRET" not in json.dumps(graph)
    with pytest.raises(ValueError, match="symlink"):
        extract_dependencies(root / "linked")


def test_limits_encoding_and_manifest(tmp_path):
    root = tmp_path / "repo"
    source(root, "a.py", "# coding: latin-1\ndef f(): pass\n")
    (root / "a.py").write_bytes((root / "a.py").read_bytes() + b"# \xe9\n")
    with pytest.raises(ValueError, match="byte limit"):
        extract_dependencies(root, max_file_bytes=5)
    with pytest.raises(ValueError, match="positive"):
        extract_dependencies(root, max_files=0)
    output = tmp_path / "output"
    result = dispatch(parser().parse_args([
        "dependencies", "--root", str(root), "--output", str(output)]))
    assert result["coverage"]["functions"] == 1
    assert result["dependencies_sha256"] == file_hash(output / "dependencies.json")
    with pytest.raises(ValueError, match="already exists"):
        write_dependencies(root, output)
    source(root, "b.py", "")
    with pytest.raises(ValueError, match="file limit"):
        extract_dependencies(root, max_files=1)


def test_change_tracking_and_duplicate_identity(tmp_path):
    source(tmp_path, "a.py", "def f(x):\n    return x\n")
    initial = extract_dependencies(tmp_path)["symbols"]
    source(tmp_path, "a.py", "\n\ndef f(x):\n    return x\n")
    assert compare_symbols(initial, extract_dependencies(tmp_path)["symbols"])[0]["status"] == "unchanged"
    source(tmp_path, "a.py", "def f(x, y=None):\n    return x\n")
    assert compare_symbols(initial, extract_dependencies(tmp_path)["symbols"])[0]["status"] == "signature_changed"
    source(tmp_path, "a.py", "def f(x):\n    return None\n")
    assert compare_symbols(initial, extract_dependencies(tmp_path)["symbols"])[0]["status"] == "body_changed"
    source(tmp_path, "a.py", "@wrapper\ndef f(x):\n    return x\n")
    assert compare_symbols(initial, extract_dependencies(tmp_path)["symbols"])[0]["status"] == "definition_changed"
    source(tmp_path, "a.py", "def f(x): pass\ndef f(x): pass\n")
    assert compare_symbols(initial, extract_dependencies(tmp_path)["symbols"])[0]["status"] == "ambiguous_identity"
    source(tmp_path, "a.py", "def renamed(x): pass\n")
    assert {r["status"] for r in compare_symbols(initial, extract_dependencies(tmp_path)["symbols"])} == {"added", "removed"}
