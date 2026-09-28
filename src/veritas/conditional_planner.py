"""Conservative two-check conditional verification planner prototype.

This module selects and accounts for plans. Runtime invocation and online evaluation
remain separate integration gates; predictions are supplied by a frozen caller artifact.
"""

import math
from decimal import Decimal

from pydantic import Field

from .schema import StrictModel


class CheckEstimate(StrictModel):
    name: str = Field(pattern=r"^[A-Z]$")
    mean_benefit: float = Field(ge=-1, le=1)
    standard_error: float = Field(ge=0, le=1)
    call_credits: float = Field(gt=0)
    token_estimate: int = Field(ge=0)


class InteractionEstimate(StrictModel):
    mean_benefit: float = Field(ge=-1, le=1)
    standard_error: float = Field(ge=0, le=1)


class PlanEvidence(StrictModel):
    evidence_sufficient: bool
    checks: list[CheckEstimate] = Field(max_length=2)
    interaction: InteractionEstimate = Field(default_factory=lambda: InteractionEstimate(
        mean_benefit=0, standard_error=0
    ))
    hard_call_credits: float = Field(ge=0)
    soft_token_limit: int = Field(gt=0)
    token_spent: int = Field(default=0, ge=0)
    planner_overhead_tokens: int = Field(default=0, ge=0)
    confidence_z: float = Field(default=1.96, ge=0)
    baseline_policy: str = "rcvov"


class ConditionalVerificationPlanner:
    """Choose at most two optional checks and keep follow-up budget reserved."""

    def __init__(self, evidence):
        self.evidence = PlanEvidence.model_validate(evidence)
        names = [check.name for check in self.evidence.checks]
        if len(names) != len(set(names)):
            raise ValueError("Check names must be unique")
        if len(names) > 2:
            raise ValueError("At most two optional checks are supported")
        self.checks = {check.name: check for check in self.evidence.checks}
        self.spent = Decimal("0")
        self.reserved = Decimal("0")
        self.tokens = self.evidence.token_spent + self.evidence.planner_overhead_tokens
        self.stopped_for_tokens = self.tokens >= self.evidence.soft_token_limit
        self.events = {}
        self.plan = self._select()

    def _select(self):
        e = self.evidence
        fallback = {
            "mode": "fallback",
            "policy": e.baseline_policy,
            "checks": [],
            "reserved_call_credits": 0.0,
            "estimated_tokens": self.tokens,
            "reason": None,
            "plans_considered": [],
        }
        if not e.evidence_sufficient:
            fallback["reason"] = "benefit evidence is insufficient"
            return fallback
        if self.stopped_for_tokens:
            fallback["reason"] = "soft token limit reached before planning"
            return fallback
        options = [()]
        options.extend((name,) for name in self.checks)
        if len(self.checks) == 2:
            options.append(tuple(self.checks))
        evaluated = []
        for names in options:
            selected = [self.checks[name] for name in names]
            cost = sum((Decimal(str(c.call_credits)) for c in selected), Decimal("0"))
            tokens = sum(c.token_estimate for c in selected)
            token_total = self.tokens + tokens
            mean = sum(c.mean_benefit for c in selected)
            variance = sum(c.standard_error**2 for c in selected)
            if len(selected) == 2:
                mean += e.interaction.mean_benefit
                variance += e.interaction.standard_error**2
            lower = mean - e.confidence_z * math.sqrt(variance)
            feasible = cost <= Decimal(str(e.hard_call_credits)) and token_total <= e.soft_token_limit
            evaluated.append({
                "checks": list(names),
                "mean_benefit": mean,
                "conservative_benefit": lower,
                "call_credits": float(cost),
                "estimated_tokens": token_total,
                "feasible": feasible,
            })
        fallback["plans_considered"] = evaluated
        choices = [row for row in evaluated if row["checks"] and row["feasible"]
                   and row["conservative_benefit"] > 0]
        if not choices:
            fallback["reason"] = "no affordable plan has positive conservative benefit"
            return fallback
        best = max(choices, key=lambda row: (row["conservative_benefit"], -row["call_credits"]))
        self.reserved = Decimal(str(best["call_credits"]))
        return {
            "mode": "conditional",
            "policy": None,
            "checks": best["checks"],
            "reserved_call_credits": float(self.reserved),
            "estimated_tokens": best["estimated_tokens"],
            "conservative_benefit": best["conservative_benefit"],
            "uncertainty_assumption": "check and pair-interaction estimate errors are independent",
            "reason": "highest positive conservative benefit among feasible plans",
            "plans_considered": evaluated,
        }

    @property
    def remaining_call_credits(self):
        return max(Decimal("0"), Decimal(str(self.evidence.hard_call_credits)) - self.spent - self.reserved)

    def can_execute(self, name):
        """Enforce trigger order and stop optional work at the soft token threshold."""
        if name not in self.plan["checks"] or name in self.events or self.stopped_for_tokens:
            return False
        ordered = self.plan["checks"]
        index = ordered.index(name)
        return all(previous in self.events for previous in ordered[:index])

    def resolve(self, name, *, reached, check_executed=False, code_changed=False,
                actual_tokens=0, check_status=None):
        """Update reservation after a trigger, result, unreachable event, or code change."""
        if name not in self.plan["checks"]:
            raise ValueError("Event is not part of the selected plan")
        if name in self.events:
            raise ValueError("Plan event has already been resolved")
        if check_executed and not self.can_execute(name):
            raise ValueError("Check is out of order or the soft token stop has been reached")
        if not isinstance(actual_tokens, int) or actual_tokens < 0:
            raise ValueError("actual_tokens must be a nonnegative integer")
        estimate = self.checks[name]
        credit = Decimal(str(estimate.call_credits))
        self.tokens += actual_tokens
        if check_executed:
            if not reached:
                raise ValueError("A check cannot execute when its trigger was not reached")
            if credit > self.reserved:
                raise ValueError("No reserved hard call credits remain for this check")
            self.reserved -= credit
            self.spent += credit
        elif not reached:
            self.reserved -= credit
        else:
            self.reserved -= credit
        self.events[name] = {
            "reached": reached,
            "check_executed": check_executed,
            "check_status": check_status,
            "code_changed": code_changed,
            "actual_tokens": actual_tokens,
            "spent_call_credits": float(self.spent),
            "reserved_call_credits": float(self.reserved),
        }
        if code_changed:
            self.reserved = Decimal("0")
            for pending in self.plan["checks"]:
                if pending not in self.events:
                    self.events[pending] = {
                        "reached": False,
                        "check_executed": False,
                        "check_status": "invalidated_by_code_change",
                        "code_changed": True,
                        "actual_tokens": 0,
                        "spent_call_credits": float(self.spent),
                        "reserved_call_credits": 0.0,
                    }
        elif self.tokens >= self.evidence.soft_token_limit:
            self.stopped_for_tokens = True
        return self.snapshot()

    def feedback(self, verdict, reason=""):
        """Keep PASS quiet; distinguish an unavailable check from negative evidence."""
        if verdict == "PASS":
            return None
        if verdict == "ERROR":
            return "Verification unavailable; this is not evidence of incorrectness. " + reason[:1000]
        if verdict in {"FAIL", "REVIEW"}:
            return "Post-edit review requests repair; this is not a ground-truth correctness label. " + reason[:1000]
        raise ValueError("Unknown optional-check verdict")

    def snapshot(self):
        return {
            "plan": self.plan,
            "spent_call_credits": float(self.spent),
            "reserved_call_credits": float(self.reserved),
            "remaining_unreserved_call_credits": float(self.remaining_call_credits),
            "token_spent_including_controller_overhead": self.tokens,
            "soft_token_limit": self.evidence.soft_token_limit,
            "stop_for_soft_token_limit": self.stopped_for_tokens,
            "events": dict(self.events),
            "fallback_policy": self.evidence.baseline_policy,
        }
