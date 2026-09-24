"""Minimal online VERITAS runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from veritas.actions.permissions import PermissionPolicy
from veritas.core.budgets import VerificationBudget
from veritas.core.state import ActionEvent, CheckpointRecord, RunState
from veritas.core.termination import TerminationPolicy
from veritas.models.base import ErrorEstimator, PolicyContext, PolicyModel
from veritas.risk.calibrator import TemperatureCalibrator
from veritas.risk.impact import ImpactModel
from veritas.risk.recovery_stats import RecoveryStatsTable
from veritas.risk.verifier_stats import VerifierStatsTable
from veritas.risk.vov import BudgetController, VovInputs, compute_vov
from veritas.sandbox.base import Sandbox
from veritas.verification.action_falsifier import ActionFalsifier
from veritas.nova.certificate import AsymmetricCertificateFalsifier
from veritas.nova.entropy_gate import EpistemicEntropyGate


@dataclass
class RuntimeConfig:
    max_steps: int = 40
    verification_budget: float = 1.0
    verification_cost: float = 0.03
    false_positive_cost: float = 0.1
    checkpoint_mutations: bool = True
    use_acf_certificates: bool = True
    use_entropy_gating: bool = False
    entropy_threshold: float = 0.5


@dataclass
class VeritasRuntime:
    policy: PolicyModel
    error_estimator: ErrorEstimator
    sandbox: Sandbox
    permission_policy: PermissionPolicy
    falsifier: ActionFalsifier
    verifier_stats: VerifierStatsTable
    recovery_stats: RecoveryStatsTable
    calibrator: TemperatureCalibrator = field(default_factory=TemperatureCalibrator)
    impact_model: ImpactModel = field(default_factory=ImpactModel)
    budget_controller: BudgetController = field(default_factory=lambda: BudgetController(lambda0=0.0, kappa=1.0))
    config: RuntimeConfig = field(default_factory=RuntimeConfig)
    event_store: JSONLEventStore | None = None

    def run(self, goal: str) -> RunState:
        state = RunState(goal=goal, verification_budget=VerificationBudget(self.config.verification_budget))
        terminator = TerminationPolicy(max_steps=self.config.max_steps)

        while not terminator.should_stop(state):
            context = PolicyContext(goal=state.goal, step_index=state.step_index, history=state.context_history())
            action = self.policy.propose_action(context)
            if action is None:
                state.termination_status = "completed"
                break

            permission = self.permission_policy.validate(action)
            if not permission.allowed:
                event = self._blocked_event(state, action, context, "; ".join(permission.reasons))
                state.record_action(event)
                self._persist(event)
                continue

            estimate = self.error_estimator.estimate(context, action)
            calibrator = TemperatureCalibrator(
                temperature=self.calibrator.temperature,
                input_is_probability=estimate.score_is_probability,
            )
            p_error = calibrator.calibrate(estimate.raw_score)
            impact = self.impact_model.score(action).value
            action_class = action.action_class.value
            verifier = self.verifier_stats.for_class(action_class)
            recovery = self.recovery_stats.for_class(action_class)
            cost = self.config.verification_cost
            hard_critical = _hard_critical(action_class, action.operation)
            vov = compute_vov(
                VovInputs(
                    p_error=p_error,
                    impact=impact,
                    detection_rate=verifier.detection_rate,
                    false_positive_rate=verifier.false_positive_rate,
                    residual_loss_after_recovery=recovery.residual_loss,
                    verification_cost=cost,
                    false_positive_cost=self.config.false_positive_cost,
                )
            )
            gate = self.budget_controller.choose(
                vov,
                cost=cost,
                remaining=float(state.verification_budget.remaining),
                total=state.verification_budget.total,
                hard_critical=hard_critical,
            )

            # EEG check: if enabled and not hard_critical, low entropy skips verification
            eeg_skip = False
            if self.config.use_entropy_gating and not hard_critical:
                gate_eeg = EpistemicEntropyGate(tau_entropy=self.config.entropy_threshold)
                action_text = f"{action.tool}.{action.operation}({action.arguments})"
                eeg_skip, _ = gate_eeg.should_skip_verification(action_text)

            verifier_verdict: str | None = None
            if gate.selected and not eeg_skip:
                state.verification_budget.spend(cost)
                verification = self.falsifier.verify(action)
                verifier_verdict = verification.verdict

                # ACF Asymmetric Falsification: objection must be proven by executable certificate
                is_real_failure = verification.verdict == "fail"
                if is_real_failure and self.config.use_acf_certificates:
                    acf = AsymmetricCertificateFalsifier()
                    acf_result = acf.check(action)
                    if acf_result.certificate is not None:
                        is_real_failure = acf_result.proven
                        if not acf_result.proven:
                            verifier_verdict = "pass"  # Unproven objection overruled

                if is_real_failure:
                    event = self._event(
                        state,
                        action,
                        estimate.raw_score,
                        p_error,
                        impact,
                        verifier.detection_rate,
                        verifier.false_positive_rate,
                        recovery.residual_loss,
                        cost,
                        vov.delta,
                        gate.selected,
                        hard_critical,
                        gate.reason,
                        verifier_verdict=verifier_verdict,
                        executed=False,
                        execution_success=False,
                    )
                    state.record_action(event)
                    self._persist(event)
                    continue

            checkpoint: CheckpointRecord | None = None
            if self.config.checkpoint_mutations and action.mutates_state:
                cp = self.sandbox.checkpoint()
                checkpoint = CheckpointRecord(cp.checkpoint_id, state.step_index, cp.state_hash, str(cp.snapshot_path))
                state.record_checkpoint(checkpoint)

            execution = self.sandbox.execute(action)
            event = self._event(
                state,
                action,
                estimate.raw_score,
                p_error,
                impact,
                verifier.detection_rate,
                verifier.false_positive_rate,
                recovery.residual_loss,
                cost,
                vov.delta,
                gate.selected,
                hard_critical,
                gate.reason,
                verifier_verdict=verifier_verdict,
                executed=True,
                execution_success=execution.ok,
                checkpoint_id=checkpoint.checkpoint_id if checkpoint else None,
            )
            state.record_action(event)
            self._persist(event)

        if state.termination_status == "running":
            state.termination_status = "max_steps"
        return state

    def _blocked_event(self, state: RunState, action, context: PolicyContext, reason: str) -> ActionEvent:
        estimate = self.error_estimator.estimate(context, action)
        calibrator = TemperatureCalibrator(
            temperature=self.calibrator.temperature,
            input_is_probability=estimate.score_is_probability,
        )
        p_error = calibrator.calibrate(estimate.raw_score)
        impact = self.impact_model.score(action).value
        return self._event(
            state,
            action,
            estimate.raw_score,
            p_error,
            impact,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            selected=False,
            hard_critical=False,
            gate_reason=f"blocked: {reason}",
            verifier_verdict="fail",
            executed=False,
            execution_success=False,
        )

    def _event(
        self,
        state: RunState,
        action,
        raw_score: float,
        p_error: float,
        impact: float,
        detection_rate: float,
        false_positive_rate: float,
        residual_loss: float,
        estimated_cost: float,
        delta: float,
        selected: bool,
        hard_critical: bool,
        gate_reason: str,
        *,
        verifier_verdict: str | None,
        executed: bool,
        execution_success: bool | None,
        checkpoint_id: str | None = None,
    ) -> ActionEvent:
        return ActionEvent(
            run_id=state.run_id,
            step=state.step_index,
            action=action,
            action_class=action.action_class.value,
            raw_error_score=raw_score,
            calibrated_error_probability=p_error,
            impact=impact,
            detection_rate_estimate=detection_rate,
            false_positive_rate_estimate=false_positive_rate,
            residual_loss_after_recovery=residual_loss,
            estimated_cost=estimated_cost,
            delta_value=delta,
            selected=selected,
            hard_critical=hard_critical,
            gate_reason=gate_reason,
            verifier_verdict=verifier_verdict,
            ground_truth_label="unresolved",
            label_source="unlabeled",
            executed=executed,
            execution_success=execution_success,
            checkpoint_id=checkpoint_id,
        )

    def _persist(self, event: ActionEvent) -> None:
        if self.event_store is not None:
            self.event_store.append(event)


def _hard_critical(action_class: str, operation: str) -> bool:
    text = f"{action_class} {operation}".lower()
    return any(word in text for word in ("destructive", "delete", "external", "payment", "credential", "push_force"))


def make_default_event_store(path: str | Path) -> JSONLEventStore:
    return JSONLEventStore(Path(path))
