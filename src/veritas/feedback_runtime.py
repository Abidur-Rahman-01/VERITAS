"""Checkpoint hook connecting the actor loop to evidence and feedback policies."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .feedback_evidence import EvidenceBank, EvidenceItem, PatchCheckpoint
from .feedback_policy import FeedbackDecision, select_feedback
from .io import digest
from .state import tree_hash


class FeedbackCheckpointController:
    """Produce/select feedback after each executed workspace-changing action.

    Pass ``on_step`` as ``run_phase(..., on_step=controller.on_step)`` and
    ``feedback_provider=controller.feedback``. Evidence production is injected so
    every arm can share the exact same check/reviewer schedule.
    """

    def __init__(self, *, task_id: str, branch_id: str, arm: str, baseline: Path,
                 workspace: Path, environment_hash: str, patch_fn: Callable,
                 evidence_producer: Callable, packet_char_cap: int = 6000,
                 adaptive_weights: dict[str, float] | None = None,
                 selector_credit_fn: Callable | None = None,
                 remaining_credits_fn: Callable | None = None,
                 event_sink: Callable | None = None):
        self.task_id = task_id
        self.branch_id = branch_id
        self.arm = arm
        self.baseline = Path(baseline)
        self.workspace = Path(workspace)
        self.environment_hash = environment_hash
        self.patch_fn = patch_fn
        self.evidence_producer = evidence_producer
        self.packet_char_cap = packet_char_cap
        self.adaptive_weights = adaptive_weights
        self.selector_credit_fn = selector_credit_fn or (lambda: 0.0)
        self.remaining_credits_fn = remaining_credits_fn or (lambda: 0.0)
        self.event_sink = event_sink
        self.bank = EvidenceBank()
        self.decisions: list[FeedbackDecision] = []
        self._packet: str | None = None
        self._delivered: set[str] = set()
        self._last_tree_hash: str | None = None

    def create_initial_checkpoint(self, session):
        """Create checkpoint 0 following the frozen draft before revision actions."""
        tree = tree_hash(self.workspace)
        patch = self.patch_fn(self.baseline, self.workspace)
        checkpoint_id = len(self.decisions)
        changed_files = _changed_paths(patch)
        remaining_credits = self.remaining_credits_fn()
        checkpoint = PatchCheckpoint(
            task_id=self.task_id, branch_id=self.branch_id, checkpoint_id=checkpoint_id,
            patch_hash=digest(patch), tree_hash=tree, environment_hash=self.environment_hash,
            changed_files=changed_files, actor_history_hash=digest(session.history),
            remaining_credits=(None if remaining_credits is None else
                               max(0.0, float(remaining_credits))),
        )
        expired = self.bank.advance(checkpoint)
        producer_error = None
        try:
            produced = list(self.evidence_producer(checkpoint, self.workspace, None, session) or [])
        except Exception as exc:
            produced = []
            producer_error = f"{type(exc).__name__}: {exc}"
        for item in produced:
            if not isinstance(item, EvidenceItem):
                raise TypeError("evidence_producer must return EvidenceItem records")
            self.bank.add(item)
        decision = select_feedback(
            arm=self.arm, branch_id=self.branch_id, checkpoint_id=checkpoint_id,
            evidence=self.bank.current(), changed_files=changed_files,
            previously_delivered=self._delivered, packet_char_cap=self.packet_char_cap,
            adaptive_weights=self.adaptive_weights,
            selector_credits=float(self.selector_credit_fn()),
        )
        self.decisions.append(decision)
        self._delivered.update(decision.selected_evidence_ids)
        self._packet = decision.packet
        self._last_tree_hash = tree
        event = {
            "checkpoint": checkpoint.model_dump(mode="json"),
            "expired_evidence_ids": expired,
            "produced_evidence": [item.model_dump(mode="json") for item in produced],
            "evidence_producer_error": producer_error,
            "decision": decision.model_dump(mode="json"),
        }
        if self.event_sink:
            self.event_sink(event)
        return event

    def on_step(self, record, session):
        if not record.executed or record.state_before == record.state_after:
            return None
        # Reads/tests do not normally change the tree. If a tool did mutate files,
        # treat the resulting state as a new checkpoint regardless of tool label.
        tree = tree_hash(self.workspace)
        if tree == self._last_tree_hash:
            return None
        patch = self.patch_fn(self.baseline, self.workspace)
        checkpoint_id = len(self.decisions)
        changed_files = _changed_paths(patch)
        remaining_credits = self.remaining_credits_fn()
        checkpoint = PatchCheckpoint(
            task_id=self.task_id, branch_id=self.branch_id, checkpoint_id=checkpoint_id,
            patch_hash=digest(patch), tree_hash=tree, environment_hash=self.environment_hash,
            changed_files=changed_files, actor_history_hash=digest(session.history),
            remaining_credits=(None if remaining_credits is None else
                               max(0.0, float(remaining_credits))),
        )
        expired = self.bank.advance(checkpoint)
        producer_error = None
        try:
            produced = list(self.evidence_producer(checkpoint, self.workspace, record, session) or [])
        except Exception as exc:
            # Check/reviewer outages do not become passes and do not abort the repair.
            produced = []
            producer_error = f"{type(exc).__name__}: {exc}"
        for item in produced:
            if not isinstance(item, EvidenceItem):
                raise TypeError("evidence_producer must return EvidenceItem records")
            self.bank.add(item)
        decision = select_feedback(
            arm=self.arm, branch_id=self.branch_id, checkpoint_id=checkpoint_id,
            evidence=self.bank.current(), changed_files=changed_files,
            previously_delivered=self._delivered, packet_char_cap=self.packet_char_cap,
            adaptive_weights=self.adaptive_weights,
            selector_credits=float(self.selector_credit_fn()),
        )
        self.decisions.append(decision)
        self._delivered.update(decision.selected_evidence_ids)
        self._packet = decision.packet
        self._last_tree_hash = tree
        event = {
            "checkpoint": checkpoint.model_dump(mode="json"),
            "expired_evidence_ids": expired,
            "produced_evidence": [item.model_dump(mode="json") for item in produced],
            "evidence_producer_error": producer_error,
            "decision": decision.model_dump(mode="json"),
        }
        if self.event_sink:
            self.event_sink(event)
        return event

    def feedback(self, session=None) -> str | None:
        """Return the most recent packet; prior packets persist until a new checkpoint."""
        return self._packet


def _changed_paths(patch: str) -> list[str]:
    paths = set()
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            paths.add(line[6:])
    return sorted(paths)
