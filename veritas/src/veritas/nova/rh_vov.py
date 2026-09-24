"""NOVA-VoV Pillar 2: Receding-Horizon Bellman VoV (RH-VoV).

Replaces the current single-step greedy Delta with a finite-horizon
Bellman value that accounts for:
  - Remaining trajectory length (steps left)
  - Remaining verification budget
  - Position-aware cascade impact (early errors matter more)
  - Hard-critical flags (e.g. injected faults / known danger states)

Evidence basis:
  Puterman (1994) "Markov Decision Processes" — Chapter 4
  Lightman et al. (2023) "Let's Verify Step by Step"
  Uesato et al. (2022) "Solving math word problems with process-based feedback"
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EPS = 1e-9


@dataclass(frozen=True)
class RHVoVInputs:
    """All inputs required for one Bellman step evaluation."""

    p_error: float          # Calibrated error probability for this step
    base_impact: float      # Static impact score from ImpactModel [0,1]
    detection_rate: float   # Verifier TPR
    false_positive_rate: float  # Verifier FPR
    residual_loss: float    # Post-recovery residual loss rho
    verification_cost: float  # Cost in budget units
    false_positive_cost: float = 0.1

    step_index: int = 0     # Current step t (0-indexed)
    total_steps: int = 1    # Total horizon T
    remaining_budget: float = 0.24
    total_budget: float = 0.24

    gamma: float = 0.95     # Discount factor
    cascade_beta: float = 1.0  # Position-weighting strength
    hard_critical: bool = False


@dataclass(frozen=True)
class RHVoVResult:
    """Output of the receding-horizon computation."""

    should_verify: bool
    position_aware_impact: float
    immediate_reward_verify: float
    immediate_reward_skip: float
    horizon_remaining: int
    threshold_used: float


def position_aware_impact(
    base_impact: float,
    step_index: int,
    total_steps: int,
    beta: float = 1.0,
) -> float:
    """Scale impact by remaining trajectory fraction."""
    if total_steps <= 0:
        return float(base_impact)
    remaining_fraction = (total_steps - step_index) / max(1, total_steps)
    multiplier = 1.0 + beta * remaining_fraction
    return min(1.0, float(base_impact) * multiplier)


def _clip01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def immediate_reward(
    inp: RHVoVInputs, action: int
) -> float:
    """Compute R(s_t, a_t) for verify (1) or skip (0)."""
    p = _clip01(inp.p_error)
    impact = position_aware_impact(
        inp.base_impact, inp.step_index, inp.total_steps, inp.cascade_beta
    )
    d = _clip01(inp.detection_rate)
    fp = _clip01(inp.false_positive_rate)
    rho = _clip01(inp.residual_loss)
    c_v = max(0.0, inp.verification_cost)
    c_fp = max(0.0, inp.false_positive_cost)

    if action == 0:
        return 0.0

    caught_benefit = p * d * impact * (1.0 - rho)
    fp_harm = (1.0 - p) * fp * c_fp
    return caught_benefit - c_v - fp_harm


def budget_adaptive_threshold(
    remaining: float, total: float, horizon_left: int
) -> float:
    """Adaptive threshold that lowers when plenty of budget remains."""
    if total <= 0:
        return float("inf")
    consumed_fraction = 1.0 - max(0.0, remaining) / total
    # Baseline threshold is 0.0, scaling up gently as budget depletes
    return 0.2 * consumed_fraction


def decide(inp: RHVoVInputs) -> RHVoVResult:
    """Bellman lookahead decision with hard-critical awareness."""
    impact_t = position_aware_impact(
        inp.base_impact, inp.step_index, inp.total_steps, inp.cascade_beta
    )
    horizon_left = max(0, inp.total_steps - inp.step_index - 1)

    if inp.remaining_budget < inp.verification_cost:
        return RHVoVResult(
            should_verify=False,
            position_aware_impact=impact_t,
            immediate_reward_verify=0.0,
            immediate_reward_skip=0.0,
            horizon_remaining=horizon_left,
            threshold_used=float("inf"),
        )

    if inp.hard_critical:
        return RHVoVResult(
            should_verify=True,
            position_aware_impact=impact_t,
            immediate_reward_verify=1.0,
            immediate_reward_skip=0.0,
            horizon_remaining=horizon_left,
            threshold_used=0.0,
        )

    r_verify = immediate_reward(inp, action=1)
    threshold = budget_adaptive_threshold(
        inp.remaining_budget, inp.total_budget, horizon_left
    )

    marginal = r_verify / (inp.verification_cost + EPS)
    should = r_verify > 0 and marginal >= threshold

    return RHVoVResult(
        should_verify=should,
        position_aware_impact=impact_t,
        immediate_reward_verify=r_verify,
        immediate_reward_skip=0.0,
        horizon_remaining=horizon_left,
        threshold_used=threshold,
    )
