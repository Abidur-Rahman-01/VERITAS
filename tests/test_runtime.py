import random
from pathlib import Path

import pytest
from conftest import BUG, FIX, WRONG, actor_policy

from veritas.agent import Agent, AgentState, initial_state
from veritas.backend import FakeBackend
from veritas.config import AgentConfig, CostConfig, EvidenceConfig
from veritas.grading import grade
from veritas.producers import ProducerContext, Producers, extract_json, parse_summary
from veritas.refset import edit_actions, materialize, reference_message
from veritas.sandbox import LocalSandbox, SandboxError, restore_sandbox
from veritas.tasks import task_from_row
from veritas.tools import ToolCall, execute
from veritas.util import stable_unit_interval


def open_repo(cfg, row):
    return LocalSandbox(cfg, row["docker_image"])


def test_sandbox_diff_tree_snapshot_restore(local_sandbox_cfg, repo_rows):
    sb = open_repo(local_sandbox_cfg, repo_rows[0])
    try:
        base_tree = sb.tree_hash()
        assert sb.diff() == ""
        sb.write_file("calc.py", sb.read_file("calc.py").replace(BUG, FIX))
        assert "+    return a + b" in sb.diff()
        tree = sb.tree_hash()
        assert tree != base_tree
        snap = sb.snapshot()
        restored = restore_sandbox(local_sandbox_cfg, repo_rows[0]["docker_image"], snap)
        try:
            assert restored.tree_hash() == tree
        finally:
            restored.close()
            sb.drop_snapshot(snap)
        with pytest.raises(SandboxError):
            sb.relpath("../outside.py")
        with pytest.raises(SandboxError):
            sb.relpath("/etc/passwd")
    finally:
        sb.close()


def test_editor_tools(local_sandbox_cfg, repo_rows):
    sb = open_repo(local_sandbox_cfg, repo_rows[0])
    try:
        view = execute(sb, ToolCall("str_replace_editor", {"command": "view", "path": "calc.py",
                                                            "view_range": [4, 5]}), 5000)
        assert "def add" in view and "4\t" in view
        dup = execute(sb, ToolCall("str_replace_editor", {"command": "str_replace",
                                                           "path": "calc.py",
                                                           "old_str": "return a - b"}), 5000)
        assert "occurs 2 times" in dup
        ok = execute(sb, ToolCall("str_replace_editor", {"command": "str_replace",
                                                          "path": "calc.py", "old_str": BUG,
                                                          "new_str": FIX}), 5000)
        assert ok.startswith("Edited")
        out = execute(sb, ToolCall("execute_bash", {"command": "python -c 'print(1+1)'"}), 5000)
        assert "exit code 0" in out and "2" in out
        created = execute(sb, ToolCall("str_replace_editor", {"command": "create",
                                                               "path": "calc.py",
                                                               "file_text": "x"}), 5000)
        assert "already exists" in created
    finally:
        sb.close()


def test_pytest_summary_parsing():
    out = ("PASSED tests/a.py::test_x\nFAILED tests/a.py::test_y - AssertionError: boom\n"
           "ERROR tests/a.py::test_z[1-2] - Exception\n")
    outcomes, messages = parse_summary(out)
    assert outcomes == {"tests/a.py::test_x": "PASSED", "tests/a.py::test_y": "FAILED",
                        "tests/a.py::test_z[1-2]": "ERROR"}
    assert messages["tests/a.py::test_y"] == "AssertionError: boom"
    assert extract_json('<think>{"no": 1}</think> text {"a": {"b": "}"}} tail') == {
        "a": {"b": "}"}
    }


def test_producers_on_wrong_patch(local_sandbox_cfg, repo_rows, fake_backend):
    sb = open_repo(local_sandbox_cfg, repo_rows[0])
    try:
        sb.write_file("calc.py", sb.read_file("calc.py").replace(BUG, WRONG))
        producers = Producers(sb, fake_backend, EvidenceConfig(), CostConfig())
        ctx = ProducerContext("t", "issue", "c1", sb.tree_hash(), sb.environment_hash, sb.diff())
        out = producers.produce(ctx)
        families = {i.family for i in out.items}
        assert {"F1", "F2", "F3", "F5", "F6", "F7"} <= families, (families, out.errors)
        f1 = next(i for i in out.items if i.family == "F1")
        assert f1.tests == ["tests/test_calc.py::test_add"] and "fails" in f1.claim
        f3 = next(i for i in out.items if i.family == "F3")
        assert "PASSING" in f3.observed
        assert all(i.patch_hash == ctx.tree_hash for i in out.items)
        assert out.credits > 0
        assert {i.basis for i in out.items if i.family in ("F5", "F6", "F7")} == {"model_opinion"}
    finally:
        sb.close()


def test_grading_semantics(local_sandbox_cfg, repo_rows):
    task = task_from_row(repo_rows[0], "swe_rebench")

    def opener():
        return LocalSandbox(local_sandbox_cfg, task.image)

    assert grade(task, task.gold_patch, local_sandbox_cfg, opener).status == "resolved"
    assert grade(task, "", local_sandbox_cfg, opener).status == "unresolved"
    bad = task.gold_patch.replace("return a + b", "return a * b")
    assert grade(task, bad, local_sandbox_cfg, opener).status == "unresolved"
    broken = "diff --git a/nope.py b/nope.py\n--- a/nope.py\n+++ b/nope.py\n@@ -1 +1 @@\n-x\n+y\n"
    result = grade(task, broken, local_sandbox_cfg, opener)
    assert result.status == "unresolved" and result.reason == "patch_apply_failed"


def test_edit_actions_reproduce_targets():
    rng = random.Random(0)
    for trial in range(200):
        lines = [f"line {rng.randint(0, 5)}\n" for _ in range(rng.randint(1, 30))]
        target = list(lines)
        for _ in range(rng.randint(1, 4)):
            op = rng.choice(["ins", "del", "mod"])
            pos = rng.randrange(len(target) + (1 if op == "ins" else 0)) if target else 0
            if op == "ins":
                target.insert(pos, f"new {trial}\n")
            elif target and op == "del":
                target.pop(min(pos, len(target) - 1))
            elif target:
                target[min(pos, len(target) - 1)] = f"mod {trial}\n"
        before, after = "".join(lines), "".join(target)
        calls = edit_actions({"f.py": before}, {"f.py": after})
        content = before
        for c in calls:
            args = c["arguments"]
            assert content.count(args["old_str"]) == 1
            content = content.replace(args["old_str"], args["new_str"], 1)
        assert content == after


def test_materialize_and_reference_formats(repo_rows):
    row = repo_rows[0]
    base = {"calc.py": (Path(row["docker_image"]) / "calc.py").read_text()}
    target = materialize(base, row["patch"], ["calc.py"])
    assert "return a + b" in target["calc.py"]
    calls = edit_actions(base, target)
    msg = reference_message(calls, base, target, "edit")
    assert msg["tool_calls"][0]["function"]["name"] == "str_replace_editor"
    diff_msg = reference_message(calls, base, target, "diff")
    assert diff_msg["content"].startswith("```diff") and "+    return a + b" in diff_msg["content"]


def test_agent_checkpoint_and_serialisation(local_sandbox_cfg, repo_rows):
    sb = open_repo(local_sandbox_cfg, repo_rows[0])
    try:
        packets = []

        def harness(view):
            from veritas.agent import Packet

            packets.append(view.index)
            return Packet("[HARNESS EVIDENCE] Checkpoint 1. Test add fails.", ["x"], 1.0)

        backend = FakeBackend(actor_policy)
        issue = f"<issue>\n{repo_rows[0]['problem_statement']}\n</issue>"
        seeds = [s for s in range(20) if stable_unit_interval(issue, str(s)) >= 0.5]
        state = initial_state(repo_rows[0]["problem_statement"], "/testbed", sb)
        agent = Agent(backend, sb, AgentConfig(max_steps=10), CostConfig(), harness, seeds[0])
        result = agent.run(state)
        assert result.termination == "finished"
        assert packets == [1, 2]  # wrong edit -> packet -> fix -> second checkpoint
        assert "return a + b" in result.final_diff
        assert result.state.harness_credits == 2.0
        clone = AgentState.from_json(result.state.to_json())
        assert clone.messages == result.state.messages
    finally:
        sb.close()


def test_producers_never_change_the_workspace(local_sandbox_cfg, repo_rows, fake_backend):
    sb = open_repo(local_sandbox_cfg, repo_rows[0])
    try:
        sb.write_file("calc.py", sb.read_file("calc.py").replace(BUG, WRONG))
        # A test with a side effect: it writes a file into the repository.
        sb.write_file("tests/test_side.py", "from calc import add\n\n\ndef test_side():\n"
                      "    open('side_effect.txt', 'w').write('x')\n    assert add(1, 2) == 3\n")
        tree = sb.tree_hash()
        producers = Producers(sb, fake_backend, EvidenceConfig(families=["F1"]), CostConfig())
        ctx = ProducerContext("t", "issue", "c1", tree, sb.environment_hash, sb.diff())
        out = producers.produce(ctx)
        assert sb.tree_hash() == tree
        assert sb.read_file("side_effect.txt") is None
        assert any("restored" in e for e in out.errors)
    finally:
        sb.close()
