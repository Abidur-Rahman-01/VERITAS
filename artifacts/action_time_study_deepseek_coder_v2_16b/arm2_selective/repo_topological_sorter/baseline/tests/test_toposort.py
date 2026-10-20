import pytest
from graphlib.toposort import topological_sort, CycleError

def test_linear_dependency():
    graph = {"build": ["compile"], "compile": ["source"], "source": []}
    res = topological_sort(graph)
    assert res.index("source") < res.index("compile") < res.index("build")

def test_diamond_dependency():
    graph = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
    res = topological_sort(graph)
    assert res.index("D") < res.index("B") < res.index("A")
    assert res.index("D") < res.index("C") < res.index("A")

def test_actual_cycle_raises():
    graph = {"A": ["B"], "B": ["C"], "C": ["A"]}
    with pytest.raises(CycleError):
        topological_sort(graph)
