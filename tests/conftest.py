"""Fixtures: small real git repositories with a bug, hidden tests, and a scripted fake actor.

The fake actor behaves like a weak repair agent: its first edit is right or wrong depending on
(task, seed); after a wrong edit it repairs the bug only if the harness packet reports a failing
test. Evidence therefore has a real, measurable effect in these fixtures.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from veritas.backend import FakeBackend, ScoreRequest
from veritas.config import SandboxConfig
from veritas.util import stable_unit_interval

CALC = '''"""Tiny calculator."""


def add(a, b):
    return a - b


def sub(a, b):
    return a - b


def mul(a, b):
    return a * b
'''
TESTS = '''from calc import add, mul, sub


def test_add():
    assert add(1, 2) == 3


def test_sub():
    assert sub(5, 3) == 2


def test_mul():
    assert mul(2, 3) == 6
'''
HIDDEN = '''from calc import add


def test_add_hidden():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
'''
CONFTEST = "import sys, os\nsys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))\n"
BUG = "def add(a, b):\n    return a - b\n"
FIX = "def add(a, b):\n    return a + b\n"
WRONG = "def add(a, b):\n    return a * b\n"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=cwd, check=True,
        capture_output=True, text=True,
    ).stdout


def make_repo(root: Path, name: str) -> dict:
    repo = root / name.replace("/", "__")
    (repo / "tests").mkdir(parents=True)
    (repo / "calc.py").write_text(CALC)
    (repo / "tests" / "test_calc.py").write_text(TESTS)
    (repo / "tests" / "conftest.py").write_text(CONFTEST)
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    base = git(repo, "rev-parse", "HEAD").strip()
    (repo / "calc.py").write_text(CALC.replace(BUG, FIX))
    gold = git(repo, "diff")
    git(repo, "checkout", "-q", "--", "calc.py")
    (repo / "tests" / "test_hidden.py").write_text(HIDDEN)
    git(repo, "add", "-N", "tests/test_hidden.py")
    test_patch = git(repo, "diff")
    git(repo, "reset", "-q")
    (repo / "tests" / "test_hidden.py").unlink()
    return {
        "instance_id": name.replace("/", "__") + "-1",
        "repo": name,
        "base_commit": base,
        "problem_statement": f"[{name}] add(1, 2) returns -1 instead of 3. Fix calc.add.",
        "patch": gold,
        "test_patch": test_patch,
        "FAIL_TO_PASS": ["tests/test_hidden.py::test_add_hidden", "tests/test_calc.py::test_add"],
        "PASS_TO_PASS": ["tests/test_calc.py::test_sub", "tests/test_calc.py::test_mul"],
        "docker_image": str(repo),
        "created_at": "2025-06-01 00:00:00",
        "install_config": {"log_parser": "parse_log_pytest"},
    }


@pytest.fixture
def local_sandbox_cfg() -> SandboxConfig:
    return SandboxConfig(kind="local", command_timeout_seconds=60, grade_timeout_seconds=120)


@pytest.fixture
def repo_rows(tmp_path) -> list[dict]:
    return [make_repo(tmp_path / "repos", f"org/repo{i}") for i in range(8)]


@pytest.fixture
def dataset(tmp_path, repo_rows) -> Path:
    path = tmp_path / "dataset.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in repo_rows))
    return path


def call(name: str, **arguments) -> str:
    return "<tool_call>" + json.dumps({"name": name, "arguments": arguments}) + "</tool_call>"


def actor_policy(messages: list[dict], seed: int) -> str:
    system = messages[0].get("content", "") if messages else ""
    last = str(messages[-1].get("content") or "")
    if "debugging assistant" in system or len(messages) == 1:
        if "Rate how likely" in last:
            return '{"score": 0.7}'
        if '"file"' in last:
            return '{"file": "calc.py", "function": "add", "root_cause": "add subtracts."}'
        if '"plan"' in last:
            return '{"plan": ["open calc.py", "make add return a + b", "run tests"]}'
        return '{"criteria": ["add(1, 2) == 3", "sub is unchanged"]}'
    issue = str(messages[1].get("content"))
    run_seed = seed // 100003
    calls = [json.loads(tc["function"]["arguments"]) | {"_name": tc["function"]["name"]}
             for m in messages if m["role"] == "assistant" for tc in m.get("tool_calls", [])]
    edits = [c for c in calls if c["_name"] == "str_replace_editor"
             and c.get("command") == "str_replace"]
    if not calls:
        return "Let me look.\n" + call("execute_bash", command="cat calc.py")
    if not edits:
        correct = stable_unit_interval(issue, str(run_seed)) < 0.5
        new = FIX if correct else WRONG
        return call("str_replace_editor", command="str_replace", path="calc.py", old_str=BUG,
                    new_str=new)
    current_wrong = edits[-1]["new_str"] == WRONG
    packet = next((str(m.get("content")) for m in reversed(messages) if m["role"] == "user"
                   and str(m.get("content", "")).startswith("[HARNESS")), "")
    if current_wrong and "fails" in packet and len(edits) < 2:
        return call("str_replace_editor", command="str_replace", path="calc.py", old_str=WRONG,
                    new_str=FIX)
    return call("finish", message="done")


def score_fn(request: ScoreRequest) -> float:
    packet = str(request.messages[-1].get("content") or "")
    value = -50.0
    if "fails" in packet:
        value += 5.0
    value -= 1.0 * packet.count("model opinion")
    value += stable_unit_interval(packet) * 0.1
    return value


@pytest.fixture
def fake_backend() -> FakeBackend:
    return FakeBackend(actor_policy, scorer=score_fn)
