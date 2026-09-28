"""CLI wiring kept separate from the legacy workflows."""


def add_parser(commands):
    sub = commands.add_parser("awareness", help="VERITAS v2 disclosure/review experiment").add_subparsers(
        dest="action", required=True)
    split = sub.add_parser("split", help="Freeze disjoint repository pools without inference")
    split.add_argument("--tasks", required=True)
    split.add_argument("--source", default="swe_rebench")
    split.add_argument("--output", required=True)
    split.add_argument("--seed", type=int, default=42)
    plan = sub.add_parser("plan", help="Freeze protocol, tasks, assignments and code hashes")
    plan.add_argument("--config", required=True)
    plan.add_argument("--output", required=True)
    for name in ("run", "resume", "grade", "audit", "report", "verify", "check-cue"):
        command = sub.add_parser(name)
        command.add_argument("--study", required=True)
        if name in {"run", "resume"}:
            command.add_argument("--max-trials", type=int)
    power = sub.add_parser("power")
    power.add_argument("--study", required=True)
    power.add_argument("--repositories", nargs="+", type=int, default=[10, 20, 40, 80])
    power.add_argument("--effects", nargs="+", type=float)
    power.add_argument("--simulations", type=int, default=2000)
    power.add_argument("--missing-probabilities", nargs="+", type=float, default=[0, 0.05, 0.15])
    power.add_argument("--bootstrap-samples", type=int, default=199)
    fit = sub.add_parser("fit-gate")
    fit.add_argument("--study", required=True)
    fit.add_argument("--output", required=True)
    cal = sub.add_parser("calibrate-gate")
    cal.add_argument("--model", required=True)
    cal.add_argument("--study", required=True)
    cal.add_argument("--confirmation", required=True)
    cal.add_argument("--output", required=True)
    cal.add_argument("--alpha", type=float, default=0.05)
    cal.add_argument("--delta", type=float, default=0.05)
    report = sub.add_parser("gate-report")
    report.add_argument("--gate", required=True)
    report.add_argument("--study", required=True)


def dispatch(args):
    from .awareness import create_splits, create_study, read_study
    from .awareness_analysis import check_manipulation, report_study
    from .awareness_power import pilot_power
    from .awareness_gate import calibrate_gate, fit_gate, report_gate
    from .awareness_runtime import audit_study, grade_study, run_study
    from .awareness_store import StudyStore

    action = args.action
    if action == "split":
        return create_splits(args.tasks, args.source, args.output, args.seed)
    if action == "plan":
        return create_study(args.config, args.output)
    if action in {"run", "resume"}:
        if args.max_trials is not None and args.max_trials < 1:
            raise ValueError("--max-trials must be positive")
        return run_study(args.study, max_trials=args.max_trials)
    if action == "grade":
        return grade_study(args.study)
    if action == "audit":
        return audit_study(args.study)
    if action == "report":
        return report_study(args.study)
    if action == "power":
        return pilot_power(args.study, args.repositories, args.effects, args.simulations,
                           args.missing_probabilities, args.bootstrap_samples)
    if action == "check-cue":
        return check_manipulation(args.study)
    if action == "fit-gate":
        return fit_gate(args.study, args.output)
    if action == "calibrate-gate":
        return calibrate_gate(args.model, args.study, args.confirmation, args.output,
                              args.alpha, args.delta)
    if action == "gate-report":
        return report_gate(args.gate, args.study)
    if action == "verify":
        plan, _, _, jobs = read_study(args.study, check_code=True)
        with StudyStore(args.study) as db:
            db.verify(plan["study_id"], jobs)
            return {"study_id": plan["study_id"], "assignments": len(jobs),
                    "integrity": "valid", "usage": db.usage()}
    raise ValueError("Unknown awareness action")
