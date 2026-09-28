"""One-shot, post-edit verification opportunities; no gold data or model access.

Runtime integration is shadow-only until the four-policy pilot runner is enabled.
The check executor is independently testable and accepts a state-review callback,
not the pre-execution Verifier (which could otherwise apply an edit twice).
"""

import math
import time
from copy import deepcopy

from .dependencies import VERSION, compare_symbols, extract_dependencies
from .io import digest
from .sanitize import redact
from .schema import Verification

RULES = {
    "version": "interface-caller-events-v1",
    "timing": "post_execution_no_rollback",
    "A": "first successful edit changing the unique target's syntactic signature",
    "B": "first successful caller signature/body edit at a later step than observed A",
    "B_fallback": "before final submission if A occurred and the unique caller still exists",
    "missing": "retain_assigned_arm_without_forced_check",
    "feedback": "FAIL/REVIEW requests repair; ERROR reports unavailable evidence; PASS is silent",
}


def _unique(snapshot, identity):
    found = [s for s in snapshot["symbols"] if s["identity"] == identity]
    return found[0] if len(found) == 1 else None


class OpportunityTracker:
    def __init__(self, target, caller, initial, final_fallback=True):
        if not target or not caller or target == caller:
            raise ValueError("Distinct target and caller identities are required")
        if initial.get("extractor") != VERSION:
            raise ValueError("Unsupported dependency extractor")
        for identity in (target, caller):
            if _unique(initial, identity) is None:
                raise ValueError(f"Initial symbol must have a unique identity: {identity}")
        self.target, self.caller = target, caller
        self.previous = deepcopy(initial)
        self.final_fallback = final_fallback
        self.events = {name: {"name": name, "status": "never_triggered", "step": None}
                       for name in ("A", "B")}
        self.diagnostics = []
        self.last_step = -1
        self.closed = False

    def _trigger(self, name, step, reason, snapshot):
        if self.events[name]["status"] != "never_triggered":
            return None
        event = {"name": name, "status": "triggered", "step": step, "reason": reason,
                 "target": self.target, "caller": self.caller,
                 "source_files_sha256": digest(snapshot["files"])}
        self.events[name] = event
        return deepcopy(event)

    def observe(self, snapshot, step, successful_edit=False, before_final=False):
        if self.closed or step <= self.last_step:
            raise ValueError("Observations require strictly increasing steps on an open tracker")
        if snapshot.get("extractor") != VERSION:
            raise ValueError("Unsupported dependency extractor")
        self.last_step = step
        result = []
        valid = not snapshot["errors"] and not self.previous["errors"]
        valid &= all(_unique(s, identity) is not None
                     for s in (self.previous, snapshot) for identity in (self.target, self.caller))
        if not valid:
            self.diagnostics.append({"step": step, "reason": "parse_error_or_missing_ambiguous_symbol"})
        else:
            changes = {r["identity"]: r["status"]
                       for r in compare_symbols(self.previous["symbols"], snapshot["symbols"])}
            if successful_edit and changes[self.target] == "signature_changed":
                event = self._trigger("A", step, "target_signature_changed", snapshot)
                if event:
                    result.append(event)
            a_step = self.events["A"]["step"]
            if a_step is not None and step > a_step:
                caller_edit = successful_edit and changes[self.caller] in {
                    "signature_changed", "body_changed"}
                fallback = before_final and self.final_fallback
                if caller_edit or fallback:
                    event = self._trigger("B", step,
                                          "caller_changed" if caller_edit else "pre_final_fallback",
                                          snapshot)
                    if event:
                        result.append(event)
        # Always advance observed state, including failed or unsupported transitions.
        # A later successful edit must not inherit a signature change from a failed tool.
        self.previous = deepcopy(snapshot)
        return result

    def handle(self, name, arm, budget, cost, check=None):
        """Reserve once, then review committed state. Skipped arms never call check.

        Returns actor feedback only for executed checks. Logs retain all decisions.
        Callback consumes a public event and returns Verification; the future runner
        must provide the matching read-only snapshot/context to its reviewer.
        """
        if self.closed or name not in self.events or self.events[name]["status"] != "triggered":
            raise ValueError("Only an unresolved triggered event can be handled")
        if arm not in {"00", "10", "01", "11"}:
            raise ValueError("Unknown verification arm")
        if not math.isfinite(cost) or cost <= 0:
            raise ValueError("Check cost must be finite and positive")
        event = self.events[name]
        if arm[0 if name == "A" else 1] == "0":
            event.update(status="skipped", decision_reason="assigned_arm")
            return None
        if not budget.can_afford(cost):
            event.update(status="budget_blocked", decision_reason="insufficient_credits")
            return None
        if check is None:
            raise ValueError("Selected affordable check requires a state-review callback")
        budget.charge(cost)
        event.update(status="checking", charged_cost=cost)
        start = time.monotonic()
        try:
            verdict = check(deepcopy(event))
            if not isinstance(verdict, Verification):
                raise ValueError("State reviewer must return Verification")
            if verdict.cost != cost:
                raise ValueError("Reviewer cost differs from reserved credits")
        except Exception as exc:
            from .schema import Usage

            verdict = Verification(verdict="ERROR", reason=f"{type(exc).__name__}: {exc}",
                                   cost=cost, usage=getattr(exc, "usage", Usage(measured=False)))
        event.update(status="infrastructure_error" if verdict.verdict == "ERROR" else "checked",
                     verification={**verdict.model_dump(mode="json"), "reason": redact(verdict.reason)},
                     seconds=time.monotonic() - start)
        if verdict.verdict == "PASS":
            return None
        prefix = ("Verification unavailable; this is not evidence of incorrectness. "
                  if verdict.verdict == "ERROR" else
                  "Post-edit review requests repair; this is not a ground-truth correctness label. ")
        return prefix + redact(verdict.reason)[:1000]

    def finish(self, reason):
        for event in self.events.values():
            if event["status"] == "triggered":
                event.update(status="skipped", decision_reason=f"unhandled_at_termination:{reason}")
        self.closed = True
        return self.report()

    def report(self):
        return deepcopy({"rules": RULES, "final_fallback": self.final_fallback,
                         "events": self.events, "diagnostics": self.diagnostics,
                         "closed": self.closed, "last_step": self.last_step})


class WorkspaceObserver:
    """Opt-in runtime shadow observer: records opportunities, never invokes checks."""

    def __init__(self, root, target, caller, final_fallback=True):
        self.root = root
        self.seconds = 0.0
        start = time.monotonic()
        self.tracker = OpportunityTracker(target, caller, extract_dependencies(root), final_fallback)
        self.seconds += time.monotonic() - start

    def observe(self, step, successful_edit=False, before_final=False):
        start = time.monotonic()
        try:
            events = self.tracker.observe(extract_dependencies(self.root), step,
                                          successful_edit, before_final)
            for event in events:
                self.tracker.events[event["name"]].update(
                    status="skipped", decision_reason="shadow_observation_only")
        except (ValueError, OSError, RecursionError) as exc:
            self.tracker.diagnostics.append({"step": step, "reason": "observer_error",
                                             "error": redact(f"{type(exc).__name__}: {exc}")})
            self.tracker.previous["errors"].append({"reason": "previous_observation_unavailable"})
        finally:
            self.seconds += time.monotonic() - start

    def finish(self, reason):
        return {**self.tracker.finish(reason), "mode": "shadow",
                "observer_seconds": self.seconds, "optional_checks_executed": 0}
