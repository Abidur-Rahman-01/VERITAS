import os

import pytest

from veritas.config import SandboxConfig
from veritas.contracts import contract
from veritas.sandbox import DockerSandbox
from veritas.schema import Proposal
from veritas.state import Checkpoint

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("VERITAS_DOCKER_TESTS") != "1",
        reason="Set VERITAS_DOCKER_TESTS=1 with Docker running",
    ),
]


def test_real_docker_files_python_sql_and_restore(tmp_path):
    sandbox = DockerSandbox(tmp_path / "work", SandboxConfig())
    sandbox.preflight()
    checkpoint = Checkpoint(sandbox.workspace, tmp_path / "snapshot")

    def execute(tool, args):
        return sandbox.execute(contract(Proposal(tool=tool, args=args)))

    assert execute("write_file", {"path": "a.py", "content": "value = 7\n"})["exit_code"] == 0
    assert "value = 7" in execute("read_file", {"path": "a.py"})["output"]
    assert "7" in execute("python", {"code": "import a; print(a.value)"})["output"]
    assert (
        execute("sql", {"database": "data.db", "query": "CREATE TABLE example (value INTEGER)"})[
            "exit_code"
        ]
        == 0
    )
    assert (
        execute(
            "sql",
            {"database": "data.db", "query": "INSERT INTO example VALUES (?)", "parameters": [3]},
        )["exit_code"]
        == 0
    )
    assert (
        "3" in execute("sql", {"database": "data.db", "query": "SELECT * FROM example"})["output"]
    )
    checkpoint.restore()
    assert list(sandbox.workspace.iterdir()) == []
    checkpoint.close()


def test_real_graph_differential_probe_has_no_workspace_side_effects(tmp_path):
    from veritas.config import GraphConfig
    from veritas.controller import Budget
    from veritas.graph_verifier import GraphVerifier
    from veritas.state import tree_hash

    sandbox = DockerSandbox(tmp_path / "work", SandboxConfig())
    sandbox.preflight()
    (sandbox.workspace / "a.py").write_text("value = 1\n")
    (sandbox.workspace / "test_a.py").write_text(
        "from a import value\ndef test_value():\n    assert value == 1\n"
    )
    before = tree_hash(sandbox.workspace)
    candidate = contract(Proposal(tool="edit_file", args={"path": "a.py", "old": "1", "new": "2"}))
    engine = GraphVerifier(
        None, SandboxConfig(), [["python", "-m", "pytest", "test_a.py", "-q"]], GraphConfig()
    )
    result, trace = engine.verify_graph(
        "software fixture", candidate, 0.02, sandbox.workspace, before, Budget(0)
    )
    assert result.verdict == "FAIL" and result.certificate["check"] == "configured_test_regression"
    assert tree_hash(sandbox.workspace) == before
    assert trace["semantic_calls"] == 0
