"""Verification scheduler baselines."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from veritas.risk.vov import BudgetController, VovInputs, compute_vov


@dataclass(frozen=True)
class SchedulerDecision:
    selected: bool
    reason: str
    score: float = 0.0


class Scheduler(Protocol):
    name: str

    def select(self, record: dict, *, remaining_budget: float, total_budget: float) -> SchedulerDecision: ...


def _get_float(record: dict, key: str, default: float = 0.0) -> float:
    val = record.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def record_cost(record: dict) -> float:
    cost = record.get("estimated_cost")
    if cost is None:
        cost = record.get("verification_cost")
    if cost is None:
        cost = 0.03
    try:
        return float(cost)
    except (ValueError, TypeError):
        return 0.03


def can_afford(record: dict, remaining_budget: float) -> bool:
    return record_cost(record) <= remaining_budget


@dataclass(frozen=True)
class NeverScheduler:
    name: str = "never"

    def select(self, record: dict, *, remaining_budget: float, total_budget: float) -> SchedulerDecision:
        return SchedulerDecision(False, "never")


@dataclass(frozen=True)
class AlwaysScheduler:
    name: str = "always"

    def select(self, record: dict, *, remaining_budget: float, total_budget: float) -> SchedulerDecision:
        return SchedulerDecision(can_afford(record, remaining_budget), "always")


@dataclass(frozen=True)
class ConfidenceScheduler:
    threshold: float = 0.5
    name: str = "confidence"

    def select(self, record: dict, *, remaining_budget: float, total_budget: float) -> SchedulerDecision:
        score = _get_float(record, "calibrated_error_probability", 0.0)
        return SchedulerDecision(score >= self.threshold and can_afford(record, remaining_budget), "p_error_threshold", score)


@dataclass(frozen=True)
class RiskScheduler:
    threshold: float = 0.5
    name: str = "risk"

    def select(self, record: dict, *, remaining_budget: float, total_budget: float) -> SchedulerDecision:
        score = _get_float(record, "impact", 0.0)
        return SchedulerDecision(score >= self.threshold and can_afford(record, remaining_budget), "impact_threshold", score)


@dataclass(frozen=True)
class ErrorImpactScheduler:
    threshold: float = 0.25
    name: str = "error_x_impact"

    def select(self, record: dict, *, remaining_budget: float, total_budget: float) -> SchedulerDecision:
        score = _get_float(record, "calibrated_error_probability", 0.0) * _get_float(record, "impact", 0.0)
        return SchedulerDecision(score >= self.threshold and can_afford(record, remaining_budget), "p_error_x_impact", score)


@dataclass(frozen=True)
class MutationOnlyScheduler:
    name: str = "mutation_only"

    def select(self, record: dict, *, remaining_budget: float, total_budget: float) -> SchedulerDecision:
        action_class = str(record.get("action_class", ""))
        selected = action_class in {"code_edit", "shell", "dependency_change", "destructive_filesystem", "external_mutation"}
        return SchedulerDecision(selected and can_afford(record, remaining_budget), "mutation_class", 1.0 if selected else 0.0)


@dataclass
class RandomBudgetMatchedScheduler:
    seed: int = 42
    name: str = "random_budget_matched"

    def priority(self, record: dict) -> float:
        """Return a stable pseudo-random priority for offline budget filling."""
        action_id = str(record.get("action_id", record.get("action_json", {}).get("action_id", "")))
        digest = hashlib.sha256(f"{self.seed}:{action_id}".encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") / float(2**64)

    def select(self, record: dict, *, remaining_budget: float, total_budget: float) -> SchedulerDecision:
        if total_budget <= 0 or not can_afford(record, remaining_budget):
            return SchedulerDecision(False, "random")
        score = self.priority(record)
        return SchedulerDecision(True, "seeded_random_budget_fill", score)


@dataclass(frozen=True)
class BavarStyleScheduler:
    threshold: float = 0.25
    name: str = "bavar_style"

    def select(self, record: dict, *, remaining_budget: float, total_budget: float) -> SchedulerDecision:
        reliability = _get_float(record, "detection_rate_estimate", 0.5) * (1.0 - _get_float(record, "false_positive_rate_estimate", 0.1))
        criticality = _get_float(record, "impact", 0.0)
        uncertainty = _get_float(record, "calibrated_error_probability", 0.0)
        budget_pressure = 1.0 if total_budget <= 0 else max(0.0, remaining_budget / total_budget)
        score = uncertainty * criticality * reliability * budget_pressure / max(record_cost(record), 1e-9)
        return SchedulerDecision(score >= self.threshold and can_afford(record, remaining_budget), "bavar_style_expected_value", score)


@dataclass(frozen=True)
class RCVOVScheduler:
    include_recovery: bool = True
    controller: BudgetController = BudgetController(lambda0=0.0, kappa=1.0)
    name: str = "rc_vov"

    def select(self, record: dict, *, remaining_budget: float, total_budget: float) -> SchedulerDecision:
        rho = _get_float(record, "residual_loss_after_recovery", 0.5) if self.include_recovery else 0.5
        vov = compute_vov(
            VovInputs(
                p_error=_get_float(record, "calibrated_error_probability", 0.0),
                impact=_get_float(record, "impact", 0.0),
                detection_rate=_get_float(record, "detection_rate_estimate", 0.5),
                false_positive_rate=_get_float(record, "false_positive_rate_estimate", 0.1),
                residual_loss_after_recovery=rho,
                verification_cost=record_cost(record),
                false_positive_cost=_get_float(record, "false_positive_cost", 0.1),
            )
        )
        decision = self.controller.choose(
            vov,
            cost=record_cost(record),
            remaining=remaining_budget,
            total=total_budget,
            hard_critical=bool(record.get("hard_critical", False)),
        )
        return SchedulerDecision(decision.selected, decision.reason, vov.delta)


def default_schedulers() -> list[Scheduler]:
    return [
        NeverScheduler(),
        AlwaysScheduler(),
        ConfidenceScheduler(),
        RiskScheduler(),
        ErrorImpactScheduler(),
        MutationOnlyScheduler(),
        RandomBudgetMatchedScheduler(),
        BavarStyleScheduler(),
        RCVOVScheduler(include_recovery=False, name="rc_vov_no_recovery"),
        RCVOVScheduler(include_recovery=True),
        NOVAVoVScheduler(),
    ]


from veritas.nova.nova_scheduler import NOVAVoVScheduler  # noqa: E402
