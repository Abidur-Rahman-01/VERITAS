import os
from pathlib import Path
import pytest

from veritas.contracts import contract
from veritas.sandbox import LocalSandbox, SandboxConfig, default_sandbox_factory
from veritas.schema import Proposal


@pytest.fixture
def sandbox_env(tmp_path):
    cfg = SandboxConfig(
        image="none",
        memory="1g",
        cpus=1,
        timeout_seconds=10,
        max_output_chars=5000,
    )
    return LocalSandbox(tmp_path, cfg), tmp_path


def test_local_sandbox_file_lifecycle(sandbox_env):
    sb, ws = sandbox_env

    # 1. Write file
    w_res = sb.execute(
        contract(
            Proposal(
                tool="write_file",
                args={"path": "calc.py", "content": "def add(a, b):\n    return a + b\n"},
            )
        )
    )
    assert w_res["exit_code"] == 0
    assert (ws / "calc.py").exists()

    # 2. Read file
    r_res = sb.execute(
        contract(
            Proposal(
                tool="read_file",
                args={"path": "calc.py", "start_line": 1, "max_lines": 10},
            )
        )
    )
    assert "def add(a, b):" in r_res["output"]

    # 3. List files
    l_res = sb.execute(
        contract(
            Proposal(
                tool="list_files",
                args={"path": ".", "limit": 10},
            )
        )
    )
    assert "calc.py" in l_res["output"]

    # 4. Edit file
    e_res = sb.execute(
        contract(
            Proposal(
                tool="edit_file",
                args={
                    "path": "calc.py",
                    "old": "return a + b",
                    "new": "return a + b + 0",
                },
            )
        )
    )
    assert e_res["exit_code"] == 0
    assert "return a + b + 0" in (ws / "calc.py").read_text(encoding="utf-8")

    # 5. Delete file
    d_res = sb.execute(
        contract(
            Proposal(
                tool="delete_file",
                args={"path": "calc.py"},
            )
        )
    )
    assert d_res["exit_code"] == 0
    assert not (ws / "calc.py").exists()


def test_local_sandbox_python_and_sql(sandbox_env):
    sb, ws = sandbox_env

    # Python execution
    p_res = sb.execute(
        contract(
            Proposal(
                tool="python",
                args={"code": "import sys; print(f'result:{10*5}')"},
            )
        )
    )
    assert p_res["exit_code"] == 0
    assert "result:50" in p_res["output"]

    # SQL execution
    sql_create = sb.execute(
        contract(
            Proposal(
                tool="sql",
                args={
                    "database": "app.db",
                    "query": "CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT);",
                    "parameters": [],
                },
            )
        )
    )
    assert sql_create["exit_code"] == 0

    sql_insert = sb.execute(
        contract(
            Proposal(
                tool="sql",
                args={
                    "database": "app.db",
                    "query": "INSERT INTO items (name) VALUES (?);",
                    "parameters": ["veritas_probe"],
                },
            )
        )
    )
    assert sql_insert["exit_code"] == 0

    sql_select = sb.execute(
        contract(
            Proposal(
                tool="sql",
                args={
                    "database": "app.db",
                    "query": "SELECT name FROM items;",
                    "parameters": [],
                },
            )
        )
    )
    assert sql_select["exit_code"] == 0
    assert "veritas_probe" in sql_select["output"]


def test_local_sandbox_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("VERITAS_SANDBOX_BACKEND", "local")
    cfg = SandboxConfig(
        image="none",
        memory="1g",
        cpus=1,
        timeout_seconds=10,
        max_output_chars=5000,
    )
    sb = default_sandbox_factory(tmp_path, cfg)
    assert isinstance(sb, LocalSandbox)
    assert sb.preflight() == "local-process-sandbox"
