from pathlib import Path
import pytest
from veritas.feedback_runner import get_task_setup_fn, evaluate_workspace, make_evidence_producer
from veritas.feedback_evidence import PatchCheckpoint
from veritas.schema import Task


def test_get_task_setup_fn():
    fn = get_task_setup_fn("swe:cmd2_790")
    assert callable(fn)
    with pytest.raises(ValueError, match="No setup function"):
        get_task_setup_fn("swe:unknown_repo_99999")


def test_evaluate_workspace_and_evidence_producer(tmp_path):
    fn = get_task_setup_fn("swe:pennylane_5100")
    ws = tmp_path / "ws"
    repo, prompt = fn(ws)
    passed, out = evaluate_workspace(ws)
    assert not passed
    assert "FAILED" in out

    task = Task(
        task_id="swe:pennylane_5100",
        group_id="swe:pennylane_5100",
        source="swe_rebench",
        source_revision="a" * 40,
        source_split="test",
        kind="swe",
        prompt=prompt,
        official_holdout=True,
        repo="PennyLaneAI/pennylane",
        base_commit="b" * 40,
    )
    producer = make_evidence_producer(task)
    cp = PatchCheckpoint(
        task_id=task.task_id,
        branch_id="branch_test",
        checkpoint_id=0,
        patch_hash="p0",
        tree_hash="t0",
        environment_hash="env0",
        changed_files=["pennylane/pauli.py"],
        actor_history_hash="h0",
        remaining_credits=10.0,
    )
    items = producer(cp, ws, None, None)
    sources = {item.source for item in items}
    # Public tests/build checks are collected on a disposable copy; no private
    # grader labels or hidden-test patches are available to this producer.
    assert {"issue", "static", "test", "build"} <= sources
    assert all(item.patch_hash == cp.patch_hash for item in items)
