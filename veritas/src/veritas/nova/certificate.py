"""NOVA-VoV Pillar 3: Asymmetric Certificate Falsification (ACF).

The verifier MUST produce a machine-checkable certificate to reject an action.
Verbal critique alone is insufficient. If no passing proof can be produced,
the verifier's objection is overruled — the action executes.

This gives a zero-false-positive rate BY CONSTRUCTION for correct actions,
because a correct action cannot produce a valid falsification certificate
against itself.

Evidence basis:
  De Moura & Bjorner (2008) "Z3: An Efficient SMT Solver" — proof certificates
  Chen et al. (2023) "CodeT" — executable test-based verification
  Zheng et al. (2023) "Judging LLM-as-a-Judge" — verbal critique failure modes
"""

from __future__ import annotations

import math
import traceback
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Certificate data structure
# ---------------------------------------------------------------------------

@dataclass
class FalsificationCertificate:
    """A verifier's claim that an action is wrong, backed by executable proof.

    Attributes
    ----------
    invariant_rule : str
        Human-readable name of the invariant being checked.
    witness : dict
        Named values the proof program operates on.
    proof_source : str
        Python source for a callable ``def check(w): ...`` that returns
        True when the witness demonstrates a violation.
    explanation : str
        Human-readable reason (logged only — does NOT influence the decision).
    """

    invariant_rule: str
    witness: dict[str, Any]
    proof_source: str
    explanation: str = ""


@dataclass
class ACFResult:
    """Outcome of running a certificate through the sandboxed executor."""

    certificate: FalsificationCertificate | None
    proven: bool          # True  → violation proven  → REJECT
    overruled: bool       # True  → no valid proof    → PASS
    reason: str
    execution_error: str = ""


# ---------------------------------------------------------------------------
# Safe Python evaluator
# ---------------------------------------------------------------------------

_SAFE_GLOBALS: dict[str, Any] = {
    "__builtins__": {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "int": int,
        "float": float,
        "bool": bool,
        "str": str,
        "len": len,
        "sum": sum,
        "all": all,
        "any": any,
        "isinstance": isinstance,
        "eval": eval,
    },
    "math": math,
}


def _execute_proof(cert: FalsificationCertificate) -> tuple[bool, str]:
    """Run the certificate's proof program against its witness.

    Returns (contradiction_proven, error_message).
    """
    try:
        code = compile(cert.proof_source, "<proof>", "exec")
        local_ns: dict[str, Any] = {}
        exec(code, dict(_SAFE_GLOBALS), local_ns)
        check_fn = local_ns.get("check")
        if not callable(check_fn):
            return False, "proof_source must define a callable 'check(w)'"
        result = check_fn(cert.witness)
        if result is True:
            return True, ""
        return False, f"check(w) returned {result!r} (not True)"
    except Exception:
        return False, traceback.format_exc(limit=3)


# ---------------------------------------------------------------------------
# Built-in invariant rules for math/calc actions
# ---------------------------------------------------------------------------

def make_arithmetic_certificate(
    expression: str,
    claimed_result: float,
    *,
    tolerance: float = 1e-4,
) -> FalsificationCertificate | None:
    """Auto-generate an arithmetic_consistency certificate for calculator actions."""
    try:
        clean = expression.replace("//", "/")
        actual = float(eval(clean, {"__builtins__": None}, {}))
    except Exception:
        return None

    # Only generate a certificate when there IS an actual discrepancy
    if abs(actual - claimed_result) <= tolerance:
        return None  # Correct → no certificate → action passes

    proof_source = (
        "def check(w):\n"
        "    expr = w['expression'].replace('//', '/')\n"
        "    try:\n"
        "        actual = float(eval(expr, {'__builtins__': None}, {}))\n"
        "    except Exception:\n"
        "        return False\n"
        "    return abs(actual - w['claimed_result']) > w['tolerance']\n"
    )
    return FalsificationCertificate(
        invariant_rule="arithmetic_consistency",
        witness={
            "expression": expression,
            "claimed_result": claimed_result,
            "tolerance": tolerance,
        },
        proof_source=proof_source,
        explanation=(
            f"Expression '{expression}' evaluates to {actual:.6f}, "
            f"but agent claimed {claimed_result:.6f} "
            f"(delta={abs(actual - claimed_result):.6f})"
        ),
    )


def make_path_safety_certificate(path: str) -> FalsificationCertificate | None:
    """Generate a path_safety certificate for filesystem path violations."""
    if not (path.startswith("/") or ".." in path.split("/")):
        return None

    proof_source = (
        "def check(w):\n"
        "    p = w['path']\n"
        "    return p.startswith('/') or '..' in p.split('/')\n"
    )
    return FalsificationCertificate(
        invariant_rule="path_safety",
        witness={"path": path},
        proof_source=proof_source,
        explanation=f"Path '{path}' escapes workspace boundary",
    )


# ---------------------------------------------------------------------------
# ACF engine
# ---------------------------------------------------------------------------

@dataclass
class AsymmetricCertificateFalsifier:
    """Core ACF engine: validate, execute, and adjudicate certificates."""

    arithmetic_tolerance: float = 1e-4

    def generate_certificate(
        self, contract: Any
    ) -> FalsificationCertificate | None:
        tool = str(getattr(contract, "tool", ""))
        args = getattr(contract, "arguments", {})

        if "calc" in tool or "math" in tool:
            expr = str(args.get("expression", ""))
            target = args.get("target")
            if expr and target is not None:
                try:
                    claimed = float(target)
                except (TypeError, ValueError):
                    claimed = 0.0
                return make_arithmetic_certificate(
                    expr, claimed, tolerance=self.arithmetic_tolerance
                )

        path = str(args.get("path", ""))
        if path:
            return make_path_safety_certificate(path)

        return None

    def adjudicate(
        self, cert: FalsificationCertificate | None
    ) -> ACFResult:
        if cert is None:
            return ACFResult(
                certificate=None,
                proven=False,
                overruled=True,
                reason="no_certificate_generated",
            )

        proven, err = _execute_proof(cert)

        if proven:
            return ACFResult(
                certificate=cert,
                proven=True,
                overruled=False,
                reason=f"certificate_proven:{cert.invariant_rule}",
            )

        return ACFResult(
            certificate=cert,
            proven=False,
            overruled=True,
            reason="certificate_proof_failed",
            execution_error=err,
        )

    def check(self, contract: Any) -> ACFResult:
        cert = self.generate_certificate(contract)
        return self.adjudicate(cert)
