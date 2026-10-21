"""Versioned, provenance-carrying evidence used by the feedback-selection study."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import Field

from .io import digest
from .schema import StrictModel


class PatchCheckpoint(StrictModel):
    task_id: str
    branch_id: str
    checkpoint_id: int = Field(ge=0)
    patch_hash: str
    tree_hash: str
    environment_hash: str
    changed_files: list[str] = Field(default_factory=list)
    actor_history_hash: str
    remaining_credits: float | None = Field(default=None, ge=0)


class EvidenceItem(StrictModel):
    evidence_id: str
    task_id: str
    branch_id: str
    checkpoint_id: int = Field(ge=0)
    source: Literal["test", "build", "static", "actor_tool", "reviewer", "issue"]
    basis: Literal["observed", "model_opinion", "public_statement"]
    patch_hash: str
    tree_hash: str
    environment_hash: str
    command: str | None = None
    raw_artifact_hash: str
    claim: str
    location: str | None = None
    observed: str | None = None
    expected_if_observed: str | None = None
    affected_files: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    related_ids: list[str] = Field(default_factory=list)
    status: Literal["current", "expired", "unavailable"] = "current"
    invalidated_reason: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cost_credits: float = Field(default=0, ge=0)

    @classmethod
    def create(cls, **values):
        values.setdefault("evidence_id", digest(values)[:24])
        return cls.model_validate(values)


class EvidenceBank:
    """Append-only evidence collection with conservative exact-state validity."""

    def __init__(self):
        self._items: list[EvidenceItem] = []
        self._current: PatchCheckpoint | None = None

    @property
    def items(self) -> tuple[EvidenceItem, ...]:
        return tuple(self._items)

    @property
    def current_checkpoint(self) -> PatchCheckpoint | None:
        return self._current

    def advance(self, checkpoint: PatchCheckpoint) -> list[str]:
        if self._current and checkpoint.checkpoint_id <= self._current.checkpoint_id:
            raise ValueError("Checkpoint IDs must increase monotonically")
        expired = []
        for index, item in enumerate(self._items):
            if item.status == "current" and (
                item.task_id != checkpoint.task_id
                or item.branch_id != checkpoint.branch_id
                or item.tree_hash != checkpoint.tree_hash
                or item.environment_hash != checkpoint.environment_hash
            ):
                if item.task_id != checkpoint.task_id or item.branch_id != checkpoint.branch_id:
                    reason = "branch_or_task_changed"
                elif item.environment_hash != checkpoint.environment_hash:
                    reason = "environment_changed"
                else:
                    reason = "patch_tree_changed"
                self._items[index] = item.model_copy(update={
                    "status": "expired",
                    "invalidated_reason": reason,
                })
                expired.append(item.evidence_id)
        self._current = checkpoint
        return expired

    def add(self, item: EvidenceItem) -> None:
        if any(x.evidence_id == item.evidence_id for x in self._items):
            raise ValueError(f"Duplicate evidence ID: {item.evidence_id}")
        if self._current is None:
            raise ValueError("Advance the bank to a checkpoint before adding evidence")
        if (item.task_id, item.branch_id, item.checkpoint_id, item.tree_hash,
            item.environment_hash) != (
            self._current.task_id, self._current.branch_id, self._current.checkpoint_id,
            self._current.tree_hash, self._current.environment_hash,
        ):
            raise ValueError("Evidence provenance must match the active checkpoint")
        self._items.append(item)

    def current(self) -> list[EvidenceItem]:
        if self._current is None:
            return []
        return [x for x in self._items if x.status == "current"
                and x.tree_hash == self._current.tree_hash
                and x.environment_hash == self._current.environment_hash]


def tool_observation_item(checkpoint: PatchCheckpoint, action: dict, observation: dict,
                          step_id: int) -> EvidenceItem:
    """Turn an executed public tool observation into a source-linked evidence card."""
    tool = action.get("tool", "unknown")
    args = action.get("args", {})
    text = str(observation.get("content", ""))
    claim = text.strip() or "The tool completed without textual output."
    affected = [str(args.get("path"))] if isinstance(args, dict) and args.get("path") else []
    return EvidenceItem.create(
        task_id=checkpoint.task_id, branch_id=checkpoint.branch_id,
        checkpoint_id=checkpoint.checkpoint_id, source="actor_tool", basis="observed",
        patch_hash=checkpoint.patch_hash, tree_hash=checkpoint.tree_hash,
        environment_hash=checkpoint.environment_hash, command=str(tool),
        raw_artifact_hash=digest(observation), claim=claim[:2000],
        affected_files=affected, cost_credits=0,
        related_ids=[f"actor-step:{step_id}"],
    )
