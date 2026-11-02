"""Evaluator-side outcome reward construction for evidence-action trajectories.

The independent grader is the only source of verified repair success. Reward records are for
offline analysis/training and must never be added to agent-visible evidence or prompts.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Literal

from pydantic import Field

from .io import digest
from .schema import StrictModel


class RepairOutcome(StrictModel):
    """Independent evaluator result; `None` means no ground-truth reward is available."""

    source: Literal["independent_grader"]
    resolved: bool | None
    official_grade_status: str
    preexisting_test_regression: bool | None = None
    # Optional, non-ground-truth shaping signal. It is ignored unless explicitly enabled and
    # marked reliable by the public-check evaluator.
    public_progress_score: float | None = Field(default=None, ge=0, le=1)
    public_progress_reliable: bool = False


class ResourceCosts(StrictModel):
    """Measured costs for the chosen feedback action and its subsequent agent step."""

    action: dict[str, float] = Field(default_factory=dict)
    subsequent_agent_step: dict[str, float] = Field(default_factory=dict)


class RewardConfig(StrictModel):
    cost_penalty: float = Field(default=0.01, ge=0)
    resource_cost_coefficients: dict[str, float] = Field(default_factory=lambda: {
        "model": 1.0, "tool": 1.0, "selector": 1.0, "other": 1.0,
    })
    regression_penalty: float = Field(default=0.0, ge=0)
    enable_intermediate_progress: bool = False
    progress_reward_weight: float = Field(default=0.0, ge=0)
    delayed_credit: Literal["terminal_only", "uniform", "discounted"] = "terminal_only"
    credit_discount: float = Field(default=0.9, gt=0, le=1)


class RewardRecord(StrictModel):
    reward_id: str
    reward: float | None
    verified_success: bool | None
    official_grade_status: str
    weighted_cost: float
    cost_by_resource: dict[str, float]
    cost_penalty: float | None
    regression_penalty: float
    progress_bonus: float
    reward_basis: str
    unavailable_reason: str | None = None


class DelayedCredit(StrictModel):
    decision_id: str
    action_id: str
    reward: float | None
    credit_method: str


def _validate_cost_map(costs: dict[str, float]) -> None:
    for resource, value in costs.items():
        if not resource or not math.isfinite(value) or value < 0:
            raise ValueError("Resource costs require nonempty names and finite nonnegative values")


def compute_outcome_reward(*, outcome: RepairOutcome, costs: ResourceCosts,
                           config: RewardConfig) -> RewardRecord:
    """Compute a scalar reward from evaluator outcome and measured operational costs.

    Default behavior is exactly: +1 for independent-grader success; `-lambda * weighted_cost`
    for verified failure. Infrastructure/grader unknowns receive no reward and cannot masquerade
    as failures. Optional regression and reliable public-progress terms are separately logged.
    """
    _validate_cost_map(costs.action)
    _validate_cost_map(costs.subsequent_agent_step)
    coefficients = config.resource_cost_coefficients
    if any(not name or not math.isfinite(value) or value < 0
           for name, value in coefficients.items()):
        raise ValueError("Resource cost coefficients must be finite and nonnegative")
    if outcome.public_progress_score is not None and not math.isfinite(outcome.public_progress_score):
        raise ValueError("Public progress score must be finite")

    combined: dict[str, float] = {}
    for values in (costs.action, costs.subsequent_agent_step):
        for resource, value in values.items():
            combined[resource] = combined.get(resource, 0.0) + float(value)
    weighted_cost = sum(value * coefficients.get(resource, coefficients.get("other", 1.0))
                        for resource, value in combined.items())
    known_grade = outcome.resolved in (True, False) and outcome.official_grade_status not in {
        "infrastructure_error", "grader_error", "ungradable", "unknown", "not_run",
    }
    if not known_grade:
        return RewardRecord(
            reward_id=digest([outcome.model_dump(mode="json"), costs.model_dump(mode="json")])[:24],
            reward=None, verified_success=None,
            official_grade_status=outcome.official_grade_status,
            weighted_cost=weighted_cost, cost_by_resource=combined,
            cost_penalty=None, regression_penalty=0.0, progress_bonus=0.0,
            reward_basis="independent_grader_unavailable",
            unavailable_reason="independent_grade_not_a_known_success_or_failure",
        )

    success = outcome.resolved is True
    cost_penalty = 0.0 if success else config.cost_penalty * weighted_cost
    regression_penalty = (config.regression_penalty
                          if outcome.preexisting_test_regression is True else 0.0)
    progress_bonus = 0.0
    if config.enable_intermediate_progress and config.progress_reward_weight > 0:
        if outcome.public_progress_reliable and outcome.public_progress_score is not None:
            progress_bonus = config.progress_reward_weight * outcome.public_progress_score
    reward = (1.0 if success else 0.0) - cost_penalty - regression_penalty + progress_bonus
    basis = "independent_grader_success" if success else "independent_grader_failure"
    if progress_bonus:
        basis += "+reliable_public_progress_shaping"
    return RewardRecord(
        reward_id=digest([outcome.model_dump(mode="json"), costs.model_dump(mode="json"),
                          config.model_dump(mode="json")])[:24],
        reward=reward, verified_success=success,
        official_grade_status=outcome.official_grade_status,
        weighted_cost=weighted_cost, cost_by_resource=combined,
        cost_penalty=cost_penalty, regression_penalty=regression_penalty,
        progress_bonus=progress_bonus, reward_basis=basis,
    )


def assign_delayed_credit(*, reward: float | None,
                          decisions: Iterable[tuple[str, str]],
                          method: Literal["terminal_only", "uniform", "discounted"] = "terminal_only",
                          discount: float = 0.9) -> list[DelayedCredit]:
    """Assign a final reward to the decisions in its trajectory without inventing outcomes."""
    if not math.isfinite(discount) or not 0 < discount <= 1:
        raise ValueError("discount must be in (0, 1]")
    rows = list(decisions)
    if len({decision_id for decision_id, _ in rows}) != len(rows):
        raise ValueError("Decision IDs in a trajectory must be unique")
    if reward is not None and not math.isfinite(reward):
        raise ValueError("reward must be finite or None")
    if not rows:
        return []
    if reward is None:
        return [DelayedCredit(decision_id=decision_id, action_id=action_id,
            reward=None, credit_method=method) for decision_id, action_id in rows]
    if method == "terminal_only":
        allocated = [0.0] * (len(rows) - 1) + [float(reward)]
    else:
        weights = ([1.0] * len(rows) if method == "uniform" else
                   [discount ** (len(rows) - index - 1) for index in range(len(rows))])
        total = sum(weights)
        allocated = [float(reward) * weight / total for weight in weights]
    return [DelayedCredit(decision_id=decision_id, action_id=action_id,
        reward=value, credit_method=method)
        for (decision_id, action_id), value in zip(rows, allocated, strict=True)]
