"""Checkpoint hook connecting the actor loop to evidence and feedback policies."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .feedback_evidence import (
    EvidenceBank,
    EvidenceItem,
    PatchCheckpoint,
    tool_observation_item,
)
from .feedback_controller import (
    BudgetContext, ControllerFeatureBuilder, EvidenceAction, FeatureInput,
    FeedbackHistoryRecord, LinUCBController, build_evidence_actions,
)
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
                 max_checkpoints: int = 4,
                 adaptive_weights: dict[str, float] | None = None,
                 linucb_controller: LinUCBController | None = None,
                 feature_builder: ControllerFeatureBuilder | None = None,
                 budget_context_fn: Callable | None = None,
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
        if max_checkpoints < 1:
            raise ValueError("max_checkpoints must be at least one")
        self.max_checkpoints = max_checkpoints
        self.adaptive_weights = adaptive_weights
        if arm == "linucb" and linucb_controller is None:
            raise ValueError("The linucb arm requires a LinUCBController")
        self.linucb_controller = linucb_controller
        self.feature_builder = feature_builder or ControllerFeatureBuilder()
        self.budget_context_fn = budget_context_fn or (lambda _session: BudgetContext())
        self.selector_credit_fn = selector_credit_fn or (lambda: 0.0)
        self.remaining_credits_fn = remaining_credits_fn or (lambda: None)
        self.event_sink = event_sink
        self.bank = EvidenceBank()
        self.decisions: list[FeedbackDecision] = []
        self._packet: str | None = None
        self._delivered: set[str] = set()
        self._last_patch_hash: str | None = None
        self._checkpoint_limit_reached = False
        self.patch_checkpoint_count = 0
        self.same_patch_refresh_count = 0
        self._action_history: list[FeedbackHistoryRecord] = []

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
        decision = self._select(checkpoint, patch, session)
        self.decisions.append(decision)
        self._delivered.update(decision.selected_evidence_ids)
        self._packet = decision.packet
        self._last_patch_hash = digest(patch)
        event = {
            "checkpoint": checkpoint.model_dump(mode="json"),
            # Capture reconstructable trajectory state alongside the chosen feedback action.
            # This is public/runtime state only; independent grader results are appended later
            # to a separate evaluator-side trajectory artifact.
            "checkpoint_patch": self.patch_fn(self.baseline, self.workspace),
            "actor_history": session.history,
            "expired_evidence_ids": expired,
            "produced_evidence": [item.model_dump(mode="json") for item in produced],
            "evidence_producer_error": producer_error,
            "decision": decision.model_dump(mode="json"),
        }
        if self.event_sink:
            self.event_sink(event)
        return event

    def on_step(self, record, session):
        if not record.executed:
            return None
        if self._checkpoint_limit_reached:
            # K limits patch snapshots. Once reached, the actor continues under
            # the same remaining budget without more evidence or feedback.
            return None
        tree = tree_hash(self.workspace)
        patch = self.patch_fn(self.baseline, self.workspace)
        patch_hash = digest(patch)
        if patch_hash != self._last_patch_hash and self.patch_checkpoint_count >= self.max_checkpoints:
            self._packet = None
            self._checkpoint_limit_reached = True
            self._last_patch_hash = patch_hash
            return None
        if patch_hash == self._last_patch_hash:
            # A test/read command can produce useful public evidence without
            # changing files. Preserve the current patch checkpoint, add the
            # observation, and refresh the packet before the next actor call.
            if not record.action or self.bank.current_checkpoint is None:
                return None
            self.same_patch_refresh_count += 1
            checkpoint = self.bank.current_checkpoint
            proposal_dict = record.action.proposal.model_dump(mode="json")
            item = tool_observation_item(
                checkpoint, proposal_dict, record.observation, record.step_id
            )
            self.bank.add(item)
            decision = self._select(checkpoint, self.patch_fn(self.baseline, self.workspace), session)
            self.decisions.append(decision)
            self._delivered.update(decision.selected_evidence_ids)
            self._packet = decision.packet
            event = {
                "checkpoint": checkpoint.model_dump(mode="json"),
                "checkpoint_patch": self.patch_fn(self.baseline, self.workspace),
                "actor_history": session.history,
                "expired_evidence_ids": [],
                "produced_evidence": [item.model_dump(mode="json")],
                "evidence_producer_error": None,
                "decision": decision.model_dump(mode="json"),
                "trigger": "tool_observation_without_patch_change",
            }
            if self.event_sink:
                self.event_sink(event)
            return event

        # A tree change creates a new patch checkpoint regardless of tool label.
        self.patch_checkpoint_count += 1
        checkpoint_id = (
            self.bank.current_checkpoint.checkpoint_id + 1
            if self.bank.current_checkpoint is not None else 0
        )
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
        decision = self._select(checkpoint, patch, session)
        self.decisions.append(decision)
        self._delivered.update(decision.selected_evidence_ids)
        self._packet = decision.packet
        self._last_patch_hash = patch_hash
        event = {
            "checkpoint": checkpoint.model_dump(mode="json"),
            "checkpoint_patch": patch,
            "actor_history": session.history,
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

    def _select(self, checkpoint: PatchCheckpoint, patch: str, session) -> FeedbackDecision:
        if self.arm != "linucb":
            return select_feedback(
                arm=self.arm, branch_id=self.branch_id,
                checkpoint_id=checkpoint.checkpoint_id,
                evidence=self.bank.current(), changed_files=checkpoint.changed_files,
                previously_delivered=self._delivered, packet_char_cap=self.packet_char_cap,
                adaptive_weights=self.adaptive_weights,
                selector_credits=float(self.selector_credit_fn()),
                remaining_credits=self.remaining_credits_fn(),
            )

        current = self.bank.current()
        feature_cost = self.linucb_controller.charge_feature_build()
        actions = build_evidence_actions(checkpoint, current,
                                         packet_char_cap=self.packet_char_cap)
        state = self.feature_builder.build(FeatureInput(
            checkpoint=checkpoint, evidence=current, patch_text=patch,
            budget=self.budget_context_fn(session), history=list(self._action_history),
        ))
        neutral = "No verifier evidence is being disclosed at this checkpoint. Continue from the task and your prior work."
        if not actions:
            return FeedbackDecision(
                branch_id=self.branch_id, checkpoint_id=checkpoint.checkpoint_id,
                arm="linucb", packet=neutral, packet_chars=len(neutral), abstained=True,
                reason_codes=["no_valid_evidence_action"],
                selector_credits=feature_cost,
                controller_state_features=state.features,
            )
        bandit_decision = self.linucb_controller.select_decision(
            state, actions
        )
        chosen = next(action for action in actions if action.action_id == bandit_decision.action_id)
        decision = FeedbackDecision(
            branch_id=self.branch_id, checkpoint_id=checkpoint.checkpoint_id,
            arm="linucb", selected_evidence_ids=chosen.evidence_ids,
            evidence_scores=[{"action_id": action_id, "score": score}
                             for action_id, score in bandit_decision.action_scores.items()],
            abstained=False, packet=chosen.packet, packet_chars=len(chosen.packet),
            selector_credits=feature_cost + bandit_decision.selector_credits,
            reason_codes=["linucb_learning" if self.linucb_controller.mode == "learning"
                          else "linucb_frozen"],
            selected_action_id=chosen.action_id,
            controller_state_features=state.features,
            predicted_score=bandit_decision.predicted_mean,
            exploration_bonus=bandit_decision.exploration_bonus,
            exploration_used=bandit_decision.exploration_bonus > 0,
            controller_decision_id=bandit_decision.decision_id,
        )
        self._action_history.append(FeedbackHistoryRecord(
            action_id=chosen.action_id, evidence_ids=chosen.evidence_ids,
        ))
        return decision


def _changed_paths(patch: str) -> list[str]:
    paths = set()
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            paths.add(line[6:])
    return sorted(paths)
