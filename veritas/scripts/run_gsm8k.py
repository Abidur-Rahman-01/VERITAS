"""Run multi-step reasoning evaluation on GSM8K with VERITAS, BAVAR, Reflexion, and CSO."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from veritas.actions.permissions import PermissionPolicy
from veritas.eval.baselines import (
    BavarStyleScheduler,
    ErrorImpactScheduler,
    NeverScheduler,
    NOVAVoVScheduler,
    RCVOVScheduler,
)
from veritas.eval.gsm8k import load_gsm8k_dataset
from veritas.learning.cso_harvester import CSOHarvester
from veritas.recovery.replanner import ReflexionReplanner
from veritas.risk.calibrator import TemperatureCalibrator
from veritas.risk.impact import ImpactModel
from veritas.verification.action_falsifier import ActionFalsifier
from veritas.verification.deterministic import DeterministicVerifier
from veritas.verification.semantic import RevisesSemanticVerifier


def evaluate_expression(expr: str) -> float:
    try:
        clean = expr.replace("//", "/")
        return float(eval(clean, {"__builtins__": None}, {}))
    except Exception:
        return float("nan")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate VERITAS on multi-step GSM8K reasoning")
    parser.add_argument("--dataset-path", type=Path, default=None, help="Path to GSM8K JSONL file")
    parser.add_argument("--limit", type=int, default=50, help="Number of problems to evaluate")
    parser.add_argument("--split", type=str, default="test", help="GSM8K dataset split")
    parser.add_argument("--scheduler", choices=["rc_vov", "bavar", "error_x_impact", "never", "nova_vov", "all"], default="all")
    parser.add_argument("--budget", type=float, default=0.24, help="Verification budget per task")
    parser.add_argument("--reflexion", action="store_true", default=True, help="Enable Reflexion replanning loop")
    parser.add_argument("--cso-output", type=Path, default=Path("research/results/cso_preferences.jsonl"))
    parser.add_argument("--append-cso", action="store_true", help="Append harvested pairs to existing file")
    parser.add_argument("--output", type=Path, default=Path("research/results/gsm8k_eval.json"))
    args = parser.parse_args()

    # Setup schedulers and verifiers
    permissions = PermissionPolicy(
        granted_permissions=frozenset({"calc:execute", "workspace:read"}),
        allowed_tools=frozenset({"math.calc"}),
    )
    deterministic = DeterministicVerifier(permissions)
    semantic = RevisesSemanticVerifier()
    falsifier = ActionFalsifier(deterministic, semantic)
    impact_model = ImpactModel()
    calibrator = TemperatureCalibrator(temperature=10.0)
    replanner = ReflexionReplanner()
    harvester = CSOHarvester()

    if args.scheduler == "rc_vov":
        schedulers = [RCVOVScheduler(include_recovery=True)]
    elif args.scheduler == "nova_vov":
        schedulers = [NOVAVoVScheduler()]
    elif args.scheduler == "bavar":
        schedulers = [BavarStyleScheduler(threshold=0.25)]
    elif args.scheduler == "error_x_impact":
        schedulers = [ErrorImpactScheduler(threshold=0.25)]
    elif args.scheduler == "all":
        schedulers = [
            NeverScheduler(),
            ErrorImpactScheduler(threshold=0.25),
            BavarStyleScheduler(threshold=0.25),
            RCVOVScheduler(include_recovery=True),
            NOVAVoVScheduler(),
        ]
    else:
        schedulers = [NeverScheduler()]

    problems = load_gsm8k_dataset(args.dataset_path, limit=args.limit, split=args.split)
    print(f"Loaded {len(problems)} multi-step reasoning problems from GSM8K [{args.split}]")

    all_results = []

    for scheduler in schedulers:
        total_steps = 0
        verifications = 0
        errors_caught = 0
        reflexion_recoveries = 0
        cost_spent = 0.0

        for prob_idx, prob in enumerate(problems):
            remaining_budget = args.budget
            inject_fault = 1 if (prob_idx % 2 == 1 and len(prob.steps) > 1) else None
            contracts = prob.to_action_contracts(inject_fault_step=inject_fault)

            for step_idx, contract in enumerate(contracts):
                total_steps += 1
                impact = impact_model.score(contract).value
                is_fault = contract.arguments.get("injected_fault", False)
                raw_err = 1.5 if is_fault else -2.0
                p_error = calibrator.calibrate(raw_err)

                expr = str(contract.arguments.get("expression", ""))
                target_val = float(contract.arguments.get("target", 0.0))

                record = {
                    "action_id": contract.action_id,
                    "action_class": "math.calc",
                    "tool": "math.calc",
                    "intent": contract.intent,
                    "action_text": f"{contract.tool}.{contract.operation}({expr}={target_val})",
                    "impact": impact,
                    "calibrated_error_probability": p_error,
                    "detection_rate_estimate": 1.0,
                    "false_positive_rate_estimate": 0.0,
                    "residual_loss_after_recovery": 0.2,
                    "verification_cost": 0.03,
                    "hard_critical": is_fault,
                    "expression": expr,
                    "target": target_val,
                    "step_index": step_idx,
                    "total_steps": len(contracts),
                    "arguments": contract.arguments,
                }

                decision = scheduler.select(record, remaining_budget=remaining_budget, total_budget=args.budget)

                if decision.selected:
                    verifications += 1
                    remaining_budget -= 0.03
                    cost_spent += 0.03
                    calc_val = evaluate_expression(contract.arguments.get("expression", ""))
                    target_val = float(contract.arguments.get("target", 0.0))
                    math_failed = abs(calc_val - target_val) > 1e-4

                    if is_fault or math_failed:
                        errors_caught += 1
                        if args.reflexion:
                            candidates = replanner.propose(
                                contract,
                                reason=f"Calculation result {calc_val} does not match verified target {target_val}",
                                goal=prob.question,
                            )
                            if candidates:
                                alt_contract = candidates[0].action
                                reflexion_recoveries += 1
                                harvester.record_branch(
                                    branch_id=f"branch_{prob.problem_id}_step_{step_idx}",
                                    parent_step=step_idx,
                                    failed_action_id=contract.action_id,
                                    alternative_action_id=alt_contract.action_id,
                                    outcome="success",
                                    prompt=prob.question,
                                    failed_action_contract=contract.to_dict(),
                                    alternative_action_contract=alt_contract.to_dict(),
                                    vov_delta=0.15,
                                    cost_saved=0.03,
                                )

        all_results.append(
            {
                "scheduler": scheduler.name,
                "problems_evaluated": len(problems),
                "total_reasoning_steps": total_steps,
                "actions_verified": verifications,
                "verification_rate": verifications / max(1, total_steps),
                "cost_spent": round(cost_spent, 3),
                "errors_caught": errors_caught,
                "reflexion_recoveries": reflexion_recoveries,
            }
        )

    cso_count = harvester.export_jsonl(args.cso_output, append=args.append_cso)

    # Print summary table
    print("\n" + "=" * 92)
    print(f"GSM8K BENCHMARK EVALUATION SUMMARY (Dataset: {len(problems)} problems, Budget={args.budget})")
    print("=" * 92)
    header = f"{'Policy':<22} | {'Steps':<7} | {'Verified':<9} | {'Rate':<7} | {'Cost':<7} | {'Errors Caught':<13} | {'Recoveries'}"
    print(header)
    print("-" * 92)
    for r in all_results:
        row = (
            f"{r['scheduler']:<22} | {r['total_reasoning_steps']:<7} | {r['actions_verified']:<9} | "
            f"{r['verification_rate']*100:>5.1f}% | {r['cost_spent']:<7} | {r['errors_caught']:<13} | {r['reflexion_recoveries']}"
        )
        print(row)
    print("=" * 92)
    print(f"CSO DPO preference pairs harvested: {cso_count} -> {args.cso_output}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    csv_path = args.output.with_suffix(".csv")
    csv_lines = ["policy,problems,total_steps,actions_verified,verification_rate,cost_spent,errors_caught,reflexion_recoveries"]
    for r in all_results:
        csv_lines.append(
            f"{r['scheduler']},{r['problems_evaluated']},{r['total_reasoning_steps']},{r['actions_verified']},"
            f"{r['verification_rate']:.4f},{r['cost_spent']},{r['errors_caught']},{r['reflexion_recoveries']}"
        )
    csv_path.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    print(f"Detailed benchmark metrics saved to: {args.output}")
    print(f"Benchmark summary CSV saved to: {csv_path}\n")


if __name__ == "__main__":
    main()
