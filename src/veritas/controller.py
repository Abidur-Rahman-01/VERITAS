import math
import random
from dataclasses import dataclass
from decimal import Decimal

POLICIES = (
    "never",
    "always",
    "random",
    "confidence",
    "risk",
    "error_impact",
    "bavar_style",
    "rcvov",
)


@dataclass(frozen=True)
class Risk:
    p_error: float
    impact: float
    detection_rate: float
    false_positive_rate: float
    residual_loss: float
    verifier_cost: float
    false_alarm_cost: float

    def __post_init__(self):
        for value in (
            self.p_error,
            self.impact,
            self.detection_rate,
            self.false_positive_rate,
            self.residual_loss,
        ):
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Risk probabilities/weights must be finite and in [0,1]")
        if not math.isfinite(self.verifier_cost) or self.verifier_cost <= 0:
            raise ValueError("Verifier cost must be finite and positive")
        if not math.isfinite(self.false_alarm_cost) or self.false_alarm_cost < 0:
            raise ValueError("False alarm cost must be finite and non-negative")

    @property
    def delta(self):
        return (
            self.p_error * self.detection_rate * (1 - self.residual_loss) * self.impact
            - self.verifier_cost
            - (1 - self.p_error) * self.false_positive_rate * self.false_alarm_cost
        )


class Budget:
    def __init__(self, total):
        if not math.isfinite(total) or total < 0:
            raise ValueError("Budget must be finite and non-negative")
        self.total = Decimal(str(total))
        self.spent = Decimal("0")

    @property
    def remaining(self):
        return self.total - self.spent

    def can_afford(self, cost):
        return Decimal(str(cost)) <= self.remaining

    def charge(self, cost):
        if not math.isfinite(cost) or cost <= 0 or not self.can_afford(cost):
            raise ValueError("Cannot charge invalid cost or exceed verification budget")
        self.spent += Decimal(str(cost))


class Controller:
    def __init__(self, policy, budget, threshold=0.0, dynamic_lambda=0.1, seed=42):
        if policy not in POLICIES:
            raise ValueError(f"Unknown policy: {policy}")
        if not math.isfinite(threshold) or not math.isfinite(dynamic_lambda) or dynamic_lambda < 0:
            raise ValueError("Invalid controller threshold")
        self.policy, self.budget = policy, Budget(budget)
        self.threshold, self.dynamic_lambda = threshold, dynamic_lambda
        self.rng = random.Random(seed)

    def score(self, risk):
        return {
            "never": -math.inf,
            "always": math.inf,
            "confidence": risk.p_error,
            "risk": risk.impact,
            "error_impact": risk.p_error * risk.impact,
            # Explicit approximation, not a claimed reproduction of BAVAR.
            "bavar_style": risk.p_error * risk.impact / risk.verifier_cost,
            "rcvov": risk.delta / risk.verifier_cost,
        }.get(self.policy, 0.0)

    def decide(self, risk):
        if self.policy == "never" or not self.budget.can_afford(risk.verifier_cost):
            return False
        if self.policy == "random":
            return self.rng.random() < max(0.0, min(1.0, self.threshold))
        threshold = self.threshold
        if self.policy == "rcvov":
            fraction_used = (
                float(self.budget.spent / self.budget.total) if self.budget.total else 1.0
            )
            threshold += self.dynamic_lambda * fraction_used / max(1.0 - fraction_used, 1e-9)
        return self.score(risk) > threshold

    def reserve(self, risk):
        """Charge before calling verifier, including failures. No overspend on retries."""
        self.budget.charge(risk.verifier_cost)
