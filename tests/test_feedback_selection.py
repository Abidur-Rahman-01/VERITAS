from types import SimpleNamespace

from veritas.feedback_evidence import EvidenceBank, EvidenceItem, PatchCheckpoint
from veritas.feedback_policy import select_feedback
from veritas.feedback_runtime import FeedbackCheckpointController
from veritas.state import tree_hash


def checkpoint(number=0, tree="tree-0", branch="branch-a"):
    return PatchCheckpoint(task_id="swe:task", branch_id=branch, checkpoint_id=number,
        patch_hash=f"patch-{number}", tree_hash=tree, environment_hash="image-digest",
        actor_history_hash="history", remaining_credits=10)


def item(cp, evidence_id="e1", claim="tests failed", source="test", files=None):
    return EvidenceItem(evidence_id=evidence_id, task_id=cp.task_id, branch_id=cp.branch_id,
        checkpoint_id=cp.checkpoint_id, source=source, basis="observed", patch_hash=cp.patch_hash,
        tree_hash=cp.tree_hash, environment_hash=cp.environment_hash,
        raw_artifact_hash="raw-hash", claim=claim, affected_files=files or [])


def test_evidence_expires_when_patch_or_environment_changes():
    bank = EvidenceBank()
    first = checkpoint()
    bank.advance(first)
    bank.add(item(first))
    assert len(bank.current()) == 1
    expired = bank.advance(checkpoint(1, "tree-1"))
    assert expired == ["e1"]
    assert bank.current() == []
    assert bank.items[0].status == "expired"
    assert bank.items[0].invalidated_reason == "patch_tree_changed"


def test_evidence_must_match_active_patch_and_checkpoint():
    bank = EvidenceBank()
    cp = checkpoint()
    bank.advance(cp)
    try:
        bank.add(item(checkpoint(1, "tree-1")))
    except ValueError as exc:
        assert "provenance" in str(exc)
    else:
        raise AssertionError("stale evidence provenance was accepted")


def test_adaptive_packet_prefers_relevant_failure_and_neutral_arm_withholds():
    cp = checkpoint()
    evidence = [
        item(cp, "irrelevant", "Build completed", "build", ["other.py"]),
        item(cp, "relevant", "AssertionError: expected 2, got 1", "test", ["pkg/fix.py"]),
    ]
    adaptive = select_feedback(arm="adaptive", branch_id=cp.branch_id, checkpoint_id=0,
        evidence=evidence, changed_files=["pkg/fix.py"])
    assert adaptive.selected_evidence_ids[0] == "relevant"
    assert "AssertionError" in adaptive.packet
    neutral = select_feedback(arm="generic_retry", branch_id=cp.branch_id, checkpoint_id=0,
        evidence=evidence, changed_files=["pkg/fix.py"])
    assert neutral.abstained
    assert not neutral.selected_evidence_ids
    assert "AssertionError" not in neutral.packet


def test_feedback_packet_respects_character_cap():
    cp = checkpoint()
    cards = [item(cp, f"e{i}", "x" * 1000) for i in range(5)]
    result = select_feedback(arm="fixed_combined", branch_id=cp.branch_id, checkpoint_id=0,
        evidence=cards, changed_files=[], packet_char_cap=1200)
    assert result.packet_chars <= 1200


def test_runtime_checkpoint_hook_generates_and_delivers_feedback(tmp_path):
    baseline = tmp_path / "baseline"
    workspace = tmp_path / "workspace"
    baseline.mkdir()
    workspace.mkdir()
    (baseline / "fix.py").write_text("value = 0\n")
    (workspace / "fix.py").write_text("value = 1\n")
    events = []

    def patch_fn(before, after):
        return "+++ b/fix.py\n-old\n+new\n"

    def produce(cp, root, record, session):
        return [EvidenceItem.create(task_id=cp.task_id, branch_id=cp.branch_id,
            checkpoint_id=cp.checkpoint_id, source="test", basis="observed",
            patch_hash=cp.patch_hash, tree_hash=cp.tree_hash,
            environment_hash=cp.environment_hash, raw_artifact_hash="test-log",
            claim="AssertionError: expected 0, got 1", affected_files=["fix.py"])]

    controller = FeedbackCheckpointController(task_id="task", branch_id="branch",
        arm="adaptive", baseline=baseline, workspace=workspace, environment_hash="image",
        patch_fn=patch_fn, evidence_producer=produce, event_sink=events.append)
    session = SimpleNamespace(history=[{"action": "write_file"}])
    record = SimpleNamespace(executed=True, state_before="before", state_after=tree_hash(workspace))
    event = controller.on_step(record, session)
    assert event["decision"]["selected_evidence_ids"]
    assert "AssertionError" in controller.feedback(session)
    assert len(events) == 1


def test_runtime_stops_creating_feedback_after_frozen_checkpoint_limit(tmp_path):
    baseline = tmp_path / "baseline"
    workspace = tmp_path / "workspace"
    baseline.mkdir()
    workspace.mkdir()
    (baseline / "fix.py").write_text("value = 0\n")
    (workspace / "fix.py").write_text("value = 1\n")
    cp = checkpoint()
    controller = FeedbackCheckpointController(task_id="swe:task", branch_id="branch-a",
        arm="adaptive", baseline=baseline, workspace=workspace, environment_hash="image-digest",
        patch_fn=lambda *_: "+++ b/fix.py\n-old\n+new\n",
        evidence_producer=lambda current, *_: [EvidenceItem.create(
            task_id=current.task_id, branch_id=current.branch_id,
            checkpoint_id=current.checkpoint_id, source="test", basis="observed",
            patch_hash=current.patch_hash, tree_hash=current.tree_hash,
            environment_hash=current.environment_hash, raw_artifact_hash="test-log",
            claim="test check failed")],
        max_checkpoints=1)
    session = SimpleNamespace(history=[])
    controller.create_initial_checkpoint(session)
    (workspace / "fix.py").write_text("value = 2\n")
    record = SimpleNamespace(executed=True, state_before="before", state_after=tree_hash(workspace))
    assert controller.on_step(record, session) is None
    assert len(controller.decisions) == 1
