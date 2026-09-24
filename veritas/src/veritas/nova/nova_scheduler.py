"""NOVA-VoV Unified Scheduler — Pillar 4 + Integration.

Combines all four pillars into a single drop-in scheduler that implements
the Scheduler protocol from eval/baselines.py, so it runs alongside every
existing baseline without modifying any existing code.

Pipeline (per step):
  Tier 0: Budget check (cannot afford → SKIP)
  Tier 1: EEG — H(x_t) < tau? → INSTANT PASS (0 verifier tokens)
  Tier 2: RH-VoV — V*(verify) > V*(skip)? → proceed or SKIP
  Tier 3: ACF — cert proven? → REJECT (+ SDCB replan depth=1) else PASS
  Pillar 4: SDCB — hard cap on replan depth (prevents 12-step churn loops)
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from veritas.nova.certificate import ACFResult, AsymmetricCertificateFalsifier
from veritas.nova.entropy_gate import EpistemicEntropyGate
from veritas.nova.rh_vov import RHVoVInputs, decide as rh_vov_decide

EPS = 1e-9


@dataclass
class NOVADecision:
    """Full audit trail for one NOVA-VoV step decision — kept out of agent ctx."""

    step_index: int
    action_text: str

    # Tier 1 EEG
    entropy: float
    eeg_skipped: bool

    # Tier 2 RH-VoV
    rh_vov_should_verify: bool = False
    position_aware_impact: float = 0.0
    reward_verify: float = 0.0
    threshold_used: float = 0.0

    # Tier 3 ACF
    acf_result: ACFResult | None = None
    acf_proven: bool = False

    # Final verdict
    final_decision: str = "pass"
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = {
            "step_index": self.step_index,
            "entropy": round(self.entropy, 5),
            "eeg_skipped": self.eeg_skipped,
            "rh_vov_should_verify": self.rh_vov_should_verify,
            "position_aware_impact": round(self.position_aware_impact, 4),
            "reward_verify": round(self.reward_verify, 5),
            "threshold_used": round(self.threshold_used, 4),
            "acf_proven": self.acf_proven,
            "final_decision": self.final_decision,
            "latency_ms": round(self.latency_ms, 1),
        }
        if self.acf_result and self.acf_result.certificate:
            d["invariant_rule"] = self.acf_result.certificate.invariant_rule
            d["acf_explanation"] = self.acf_result.certificate.explanation
        return d


class SidecarLog:
    """All verification deliberation stored here — never touches agent prompt."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def record(self, decision: NOVADecision) -> None:
        self._entries.append(decision.to_dict())

    @property
    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)

    def stats(self) -> dict[str, Any]:
        if not self._entries:
            return {}
        n = len(self._entries)
        eeg_pass = sum(1 for e in self._entries if e["eeg_skipped"])
        acf_caught = sum(1 for e in self._entries if e["acf_proven"])
        avg_entropy = sum(e["entropy"] for e in self._entries) / n
        return {
            "total_steps": n,
            "eeg_instant_pass": eeg_pass,
            "eeg_pass_rate": round(eeg_pass / n, 3),
            "acf_rejections": acf_caught,
            "avg_entropy": round(avg_entropy, 4),
            "verifier_calls": n - eeg_pass,
        }


@dataclass
class NOVAVoVScheduler:
    """Unified NOVA-VoV scheduler — implements eval/baselines.Scheduler protocol."""

    name: str = "nova_vov"
    tau_entropy: float = 0.5
    cascade_beta: float = 1.0
    replan_depth_limit: int = 1
    model: str = "qwen2.5-coder:7b"
    base_url: str = "http://localhost:11434"
    arithmetic_tolerance: float = 1e-4

    _eeg: EpistemicEntropyGate = field(init=False)
    _acf: AsymmetricCertificateFalsifier = field(init=False)
    _sidecar: SidecarLog = field(init=False)
    _replan_depth: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self._eeg = EpistemicEntropyGate(
            tau_entropy=self.tau_entropy,
            model=self.model,
            base_url=self.base_url,
        )
        self._acf = AsymmetricCertificateFalsifier(
            arithmetic_tolerance=self.arithmetic_tolerance
        )
        self._sidecar = SidecarLog()
        self._replan_depth = 0

    def select(
        self,
        record: dict[str, Any],
        *,
        remaining_budget: float,
        total_budget: float,
    ) -> "SchedulerDecision":
        from veritas.eval.baselines import SchedulerDecision

        t0 = time.perf_counter()
        step_idx = int(record.get("step_index", 0))
        total_steps = int(record.get("total_steps", 1))
        action_text = str(record.get("action_text", record.get("intent", "")))
        verification_cost = float(record.get("verification_cost", 0.03))
        hard_critical = bool(record.get("hard_critical", False))

        decision = NOVADecision(
            step_index=step_idx,
            action_text=action_text,
            entropy=0.0,
            eeg_skipped=False,
        )

        # ── Tier 0: budget check ─────────────────────────────────────────
        if verification_cost > remaining_budget:
            decision.final_decision = "pass"
            decision.eeg_skipped = True
            decision.entropy = 0.0
            decision.latency_ms = (time.perf_counter() - t0) * 1000
            self._sidecar.record(decision)
            return SchedulerDecision(False, "nova_budget_exhausted", 0.0)

        # ── Tier 1: EEG (skip only if not hard_critical) ─────────────────
        if not hard_critical:
            skip_verify, entropy = self._eeg.should_skip_verification(action_text)
            decision.entropy = entropy
            if skip_verify:
                decision.eeg_skipped = True
                decision.final_decision = "pass"
                decision.latency_ms = (time.perf_counter() - t0) * 1000
                self._sidecar.record(decision)
                return SchedulerDecision(False, "nova_eeg_instant_pass", entropy)

        # ── Tier 2: RH-VoV ───────────────────────────────────────────────
        rh_inp = RHVoVInputs(
            p_error=_get_float(record, "calibrated_error_probability", 0.3),
            base_impact=_get_float(record, "impact", 0.3),
            detection_rate=_get_float(record, "detection_rate_estimate", 1.0),
            false_positive_rate=_get_float(record, "false_positive_rate_estimate", 0.0),
            residual_loss=_get_float(record, "residual_loss_after_recovery", 0.2),
            verification_cost=verification_cost,
            false_positive_cost=_get_float(record, "false_positive_cost", 0.1),
            step_index=step_idx,
            total_steps=total_steps,
            remaining_budget=remaining_budget,
            total_budget=total_budget,
            cascade_beta=self.cascade_beta,
            hard_critical=hard_critical,
        )
        rh_result = rh_vov_decide(rh_inp)
        decision.rh_vov_should_verify = rh_result.should_verify
        decision.position_aware_impact = rh_result.position_aware_impact
        decision.reward_verify = rh_result.immediate_reward_verify
        decision.threshold_used = rh_result.threshold_used

        if not rh_result.should_verify:
            decision.final_decision = "pass"
            decision.latency_ms = (time.perf_counter() - t0) * 1000
            self._sidecar.record(decision)
            return SchedulerDecision(False, "nova_rh_vov_below_threshold", rh_result.immediate_reward_verify)

        # ── Tier 3: ACF ──────────────────────────────────────────────────
        contract_proxy = _RecordProxy(record)
        acf_result = self._acf.check(contract_proxy)
        decision.acf_result = acf_result
        decision.acf_proven = acf_result.proven

        if acf_result.proven:
            decision.final_decision = "reject"
            decision.latency_ms = (time.perf_counter() - t0) * 1000
            self._sidecar.record(decision)
            return SchedulerDecision(True, f"nova_acf_proven:{acf_result.reason}", 1.0)

        # ACF overruled — pass despite RH-VoV saying to verify
        decision.final_decision = "pass"
        decision.latency_ms = (time.perf_counter() - t0) * 1000
        self._sidecar.record(decision)
        return SchedulerDecision(False, "nova_acf_overruled", 0.0)

    def reset_replan_depth(self) -> None:
        self._replan_depth = 0

    def increment_replan(self) -> bool:
        self._replan_depth += 1
        return self._replan_depth <= self.replan_depth_limit

    @property
    def sidecar(self) -> SidecarLog:
        return self._sidecar

    def summary(self) -> dict[str, Any]:
        return self._sidecar.stats()


def _get_float(record: dict, key: str, default: float = 0.0) -> float:
    val = record.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


class _RecordProxy:
    def __init__(self, record: dict[str, Any]) -> None:
        self._r = record

    @property
    def tool(self) -> str:
        return str(self._r.get("tool", self._r.get("action_class", "")))

    @property
    def arguments(self) -> dict[str, Any]:
        args = self._r.get("arguments", {})
        if isinstance(args, dict):
            return args
        out: dict[str, Any] = {}
        for k in ("expression", "target", "path", "command"):
            if k in self._r:
                out[k] = self._r[k]
        return out
