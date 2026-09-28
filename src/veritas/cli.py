import argparse
import importlib.metadata
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

from .io import canonical


def parser():
    p = argparse.ArgumentParser(
        prog="veritas", description="Real-data, local-model VERITAS experiments"
    )
    commands = p.add_subparsers(dest="command", required=True)
    from .awareness_cli import add_parser

    add_parser(commands)
    scope = commands.add_parser(
        "dependency-scope", help="Create public-only development interface/caller review queue"
    )
    scope.add_argument("--tasks", default="data/prepared")
    scope.add_argument("--source")
    scope.add_argument("--output", required=True)
    dependencies = commands.add_parser(
        "dependencies", help="Extract conservative Python dependency candidates without execution"
    )
    dependencies.add_argument("--root", required=True)
    dependencies.add_argument("--output", required=True)
    dependencies.add_argument("--max-file-bytes", type=int, default=1_000_000)
    dependencies.add_argument("--max-files", type=int, default=10_000)
    cohort = commands.add_parser(
        "dependency-cohort", help="Prepare independent reviews or freeze a reviewed pilot cohort"
    ).add_subparsers(dest="action", required=True)
    verify = cohort.add_parser("verify")
    verify.add_argument("directory")
    for action in ("prepare", "finalize"):
        command = cohort.add_parser(action)
        command.add_argument("--scope", required=True)
        command.add_argument("--output", required=True)
        if action == "finalize":
            command.add_argument("--tasks", default="data/prepared")
            command.add_argument("--reviews", required=True)
            command.add_argument("--protocol", required=True)
            command.add_argument("--config", required=True)
    pilot = commands.add_parser(
        "dependency-pilot", help="Plan/run/resume/report the four-arm dependency pilot"
    )
    pilot.add_argument("--config", required=True)
    pilot.add_argument("--output", required=True)
    mode = pilot.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--report", action="store_true")
    pilot.add_argument("--retry-failed", action="store_true")
    analysis = commands.add_parser(
        "dependency-analyze", help="Estimate cluster-aware four-arm effects from a dependency pilot"
    )
    analysis.add_argument("--output", required=True, help="Existing dependency-pilot directory")
    analysis.add_argument("--seed", type=int, default=42)
    benefit = commands.add_parser(
        "dependency-fit", help="Fit leakage-aware benefit models from an active dependency pilot"
    )
    benefit.add_argument("--output", required=True, help="Existing dependency-pilot directory")
    benefit.add_argument("--seed", type=int, default=42)
    benefit.add_argument("--validation-fraction", type=float, default=0.25)
    benefit.add_argument("--regularization", type=float, default=1.0)
    allocation = commands.add_parser(
        "dependency-allocate", help="Run a propensity-recording adaptive dependency allocator"
    )
    allocation.add_argument("--output", required=True)
    allocation_mode = allocation.add_mutually_exclusive_group(required=True)
    allocation_mode.add_argument("--init", action="store_true")
    allocation_mode.add_argument("--next", action="store_true")
    allocation_mode.add_argument("--record", action="store_true")
    allocation_mode.add_argument("--report", action="store_true")
    allocation.add_argument("--candidates")
    allocation.add_argument("--budget", type=float)
    allocation.add_argument("--cost", type=float, default=1.0)
    allocation.add_argument("--exploration", type=float, default=0.2)
    allocation.add_argument("--graph-weight", type=float, default=0.5)
    allocation.add_argument("--seed", type=int, default=42)
    allocation.add_argument("--candidate-id")
    allocation.add_argument("--arm", choices=("00", "10", "01", "11"))
    allocation.add_argument("--success", type=int, choices=(0, 1))
    allocation.add_argument("--selection-probability", type=float)
    evaluation = commands.add_parser(
        "dependency-evaluate", help="Freeze confirmation evaluation or summarize its complete ledger"
    )
    evaluation.add_argument("--output", required=True)
    evaluation_mode = evaluation.add_mutually_exclusive_group(required=True)
    evaluation_mode.add_argument("--freeze", action="store_true")
    evaluation_mode.add_argument("--report", action="store_true")
    evaluation.add_argument("--cohort")
    evaluation.add_argument("--methods")
    evaluation.add_argument("--results")
    evaluation.add_argument("--seed", type=int, default=42)
    release = commands.add_parser(
        "dependency-release", help="Create or verify a checksummed research source manifest"
    )
    release.add_argument("--root", required=True)
    release.add_argument("--output")
    release.add_argument("--verify", metavar="MANIFEST")
    release.add_argument("files", nargs="*")
    suite = commands.add_parser("suite", help="Run a resumable model/benchmark/parameter matrix")
    suite.add_argument("--config", default="configs/suite.yaml")
    suite.add_argument("--output", required=True)
    mode = suite.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--resume", action="store_true")
    mode.add_argument("--report", action="store_true")
    suite.add_argument("--retry-failed", action="store_true")
    comparison = commands.add_parser(
        "compare", help="Plan/run/resume paired local-model comparisons"
    )
    comparison.add_argument("--config", default="configs/comparison.yaml")
    comparison.add_argument("--output", required=True)
    comparison.add_argument("--models", nargs="+")
    comparison.add_argument("--sources", nargs="+")
    size = comparison.add_mutually_exclusive_group()
    size.add_argument("--limit", type=int)
    size.add_argument("--all-tasks", action="store_true")
    mode = comparison.add_mutually_exclusive_group()
    mode.add_argument(
        "--execute", action="store_true", help="Create plan and start local inference"
    )
    mode.add_argument("--resume", action="store_true", help="Run pending jobs in an existing plan")
    mode.add_argument("--report", action="store_true", help="Show saved results; no inference")
    comparison.add_argument("--retry-failed", action="store_true")
    diagnose = commands.add_parser(
        "diagnose-run", help="Audit partial runs and calibration without inference"
    )
    diagnose.add_argument("directory")
    diagnose.add_argument("--artifact")
    doctor = commands.add_parser(
        "doctor", help="Validate installation/configuration without model inference"
    )
    doctor.add_argument("--config", default="configs/experiment.yaml")
    doctor.add_argument(
        "--check-models", action="store_true", help="Read model-server metadata only"
    )
    data = commands.add_parser("data", help="Download/normalize original datasets").add_subparsers(
        dest="action", required=True
    )
    d = data.add_parser("download")
    d.add_argument("--manifest", default="configs/datasets.yaml")
    d.add_argument(
        "--sources",
        nargs="+",
        default=[
            "swe_train",
            "swe_dev",
            "swe_test",
            "swe_verified",
            "gsm8k_train",
            "gsm8k_test",
            "math500",
            "swe_rebench",
        ],
    )
    d.add_argument("--output", default="data/raw")
    d.add_argument("--limit", type=int)
    d = data.add_parser("prepare")
    d.add_argument("--manifest", default="configs/datasets.yaml")
    d.add_argument("--raw", default="data/raw")
    d.add_argument("--output", default="data/prepared")
    d.add_argument("--seed", type=int, default=42)
    d.add_argument(
        "--research-pool",
        nargs="*",
        default=[],
        choices=["swe_test", "swe_rebench"],
        help="Declare a new task-disjoint research split for these releases; Verified remains held out",
    )
    collect = commands.add_parser(
        "collect", help="Run local models on real tasks (explicitly starts inference)"
    )
    collect.add_argument("--tasks", default="data/prepared")
    collect.add_argument("--config", default="configs/experiment.yaml")
    collect.add_argument(
        "--override", action="append", help="Merge YAML override; may be repeated in order"
    )
    collect.add_argument("--output", required=True)
    collect.add_argument("--split", choices=["dev", "calib", "val", "test", "backbone"])
    collect.add_argument("--source")
    collect.add_argument("--limit", type=int)
    collect.add_argument("--artifact")
    collect.add_argument("--critic-dir")
    collect.add_argument("--images")
    collect.add_argument("--tuning", help="Frozen validation thresholds for online evaluation")
    collect.add_argument("--policy")
    collect.add_argument("--budget", type=float)
    store = commands.add_parser("store").add_subparsers(dest="action", required=True)
    s = store.add_parser("export")
    s.add_argument("database")
    s.add_argument("--output", required=True)
    s.add_argument("--encrypt-env")
    s = store.add_parser("verify")
    s.add_argument("directory")
    s = store.add_parser("decrypt")
    s.add_argument("input")
    s.add_argument("--output", required=True)
    s.add_argument("--key-env", default="VERITAS_EXPORT_KEY")
    labels = commands.add_parser("labels").add_subparsers(dest="action", required=True)
    s = labels.add_parser("queue")
    s.add_argument("records")
    s.add_argument("--output", required=True)
    s = labels.add_parser("apply")
    s.add_argument("records")
    s.add_argument("annotations")
    s.add_argument("--output", required=True)
    critic = commands.add_parser("critic").add_subparsers(dest="action", required=True)
    for name in ["train-linear", "train-lora"]:
        c = critic.add_parser(name)
        c.add_argument("records")
        c.add_argument("--output", required=True)
        c.add_argument("--scope", default="semantic", choices=["semantic", "operational"])
        c.add_argument("--seed", type=int, default=42)
        if name == "train-lora":
            c.add_argument("--model-path", required=True)
            c.add_argument("--epochs", type=float, default=2)
            c.add_argument("--batch-size", type=int, default=1)
            c.add_argument("--accumulation", type=int, default=16)
            c.add_argument("--max-length", type=int, default=2048)
    c = critic.add_parser("score")
    c.add_argument("records")
    c.add_argument("--critic-dir", required=True)
    c.add_argument("--output", required=True)
    c = commands.add_parser("calibrate")
    c.add_argument("records")
    c.add_argument("--output", required=True)
    c.add_argument("--scope", default="semantic", choices=["semantic", "operational"])
    c.add_argument("--min-class-samples", type=int, default=5)
    c = commands.add_parser(
        "validate-calibration", help="Assess held-out critic quality without inference"
    )
    c.add_argument("records")
    c.add_argument("--artifact", required=True)
    c.add_argument("--output", required=True)
    c.add_argument("--split", default="val", choices=["val", "test", "backbone"])
    for name in ["tune", "replay"]:
        c = commands.add_parser(name)
        c.add_argument("records")
        c.add_argument("--artifact", required=True)
        c.add_argument("--output", required=True)
        c.add_argument("--budgets", nargs="+", type=float, default=[0.02, 0.04, 0.1, 0.2, 0.4])
        c.add_argument("--scope", default="semantic", choices=["semantic", "operational"])
        c.add_argument("--seed", type=int, default=42)
        if name == "tune":
            c.add_argument("--dynamic-lambda", type=float, default=0.0)
        if name == "replay":
            c.add_argument("--tuning", required=True)
            c.add_argument("--split", default="test", choices=["test", "backbone", "val"])
    c = commands.add_parser("report")
    c.add_argument("directory")
    c = commands.add_parser("online-report")
    c.add_argument("summaries")
    c.add_argument("--swe-report")
    c.add_argument("--output", required=True)
    c = commands.add_parser("recovery-report")
    c.add_argument("checkpoint")
    c.add_argument("restart")
    c.add_argument("--output", required=True)
    swe = commands.add_parser("swe").add_subparsers(dest="action", required=True)
    c = swe.add_parser("image-map")
    c.add_argument("--tasks", default="data/prepared")
    c.add_argument("--output", required=True)
    c.add_argument("--split", default="test")
    c.add_argument("--source", default="swe_verified")
    c.add_argument("--limit", type=int)
    c.add_argument("--namespace", default="swebench")
    c.add_argument("--arch", default="x86_64", choices=["x86_64", "arm64"])
    c = swe.add_parser("pull-images")
    c.add_argument("mapping")
    c = swe.add_parser("build-images")
    c.add_argument("dataset")
    c.add_argument("--workers", type=int, default=2)
    c.add_argument("--arch", default="x86_64", choices=["x86_64", "arm64"])
    c = swe.add_parser("evaluate")
    c.add_argument("--dataset", required=True)
    c.add_argument("--predictions", required=True)
    c.add_argument("--run-id", required=True)
    c.add_argument("--workers", type=int, default=2)
    c.add_argument("--execute", action="store_true")
    c.add_argument("--namespace", default="swebench")
    return p


def doctor(config_path, check_models=False):
    from .config import load_config

    cfg = load_config(config_path)
    result = {
        "python": sys.version.split()[0],
        "configuration": "valid",
        "docker": "not installed",
        "versions": {
            name: importlib.metadata.version(name)
            for name in [
                "veritas-research",
                "pydantic",
                "datasets",
                "numpy",
                "pyarrow",
                "scikit-learn",
            ]
        },
        "models_invoked": False,
    }
    if shutil.which("docker"):
        docker = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        result["docker"] = (
            docker.stdout.strip()
            if docker.returncode == 0
            else "daemon unavailable; start Docker before collection"
        )
    if check_models:
        import httpx

        servers = {}
        active_models = [cfg.model]
        if cfg.run.score_critic:
            active_models.append(cfg.critic)
        if cfg.run.audit_all or (
            cfg.run.policy != "never"
            and (
                cfg.run.policy != "graph"
                or (cfg.graph.semantic_final_review and cfg.graph.max_semantic_calls)
            )
        ):
            active_models.append(cfg.verifier)
        for model in active_models:
            if model.backend == "transformers":
                servers[model.name] = (
                    "local path exists" if Path(model.name).exists() else "missing local model path"
                )
            else:
                endpoint = "/api/tags" if model.backend == "ollama" else "/models"
                response = httpx.get(model.base_url.rstrip("/") + endpoint, timeout=10)
                response.raise_for_status()
                servers[model.base_url] = response.json()
        result["servers"] = servers
    return result


def dispatch(a):
    if a.command == "awareness":
        from .awareness_cli import dispatch as dispatch_awareness

        return dispatch_awareness(a)
    if a.command == "dependencies":
        from .dependencies import write_dependencies

        return write_dependencies(a.root, a.output, a.max_file_bytes, a.max_files)
    if a.command == "dependency-cohort":
        from .dependency_cohort import finalize_cohort, prepare_reviews, verify_cohort

        if a.action == "verify":
            return verify_cohort(a.directory)
        if a.action == "prepare":
            return prepare_reviews(a.scope, a.output)
        return finalize_cohort(
            a.scope, a.tasks, a.reviews, a.protocol, a.config, a.output
        )
    if a.command == "dependency-scope":
        from .dependency_scope import create_scope

        return create_scope(a.tasks, a.output, a.source)
    if a.command == "dependency-pilot":
        from .dependency_pilot import create_pilot, report_pilot, run_pilot

        if a.retry_failed and not a.resume:
            raise ValueError("--retry-failed requires --resume")
        if a.report:
            return report_pilot(a.output)
        if not a.resume:
            create_pilot(a.config, a.output)
        if a.execute or a.resume:
            return run_pilot(a.output, a.retry_failed)
        return None
    if a.command == "dependency-analyze":
        from .dependency_analysis import analyze_pilot

        return analyze_pilot(a.output, a.seed)
    if a.command == "dependency-fit":
        from .dependency_models import fit_benefit_models

        return fit_benefit_models(
            a.output, a.seed, a.validation_fraction, a.regularization
        )
    if a.command == "dependency-allocate":
        from .dependency_allocation import (
            allocation_report,
            create_allocation,
            record_result,
            select_next,
        )

        if a.init:
            if not a.candidates or a.budget is None:
                raise ValueError("--init requires --candidates and --budget")
            return create_allocation(
                a.candidates, a.output, a.budget, a.cost,
                a.exploration, a.graph_weight, a.seed,
            )
        if a.next:
            return select_next(a.output)
        if a.record:
            if a.candidate_id is None or a.arm is None or a.success is None or a.selection_probability is None:
                raise ValueError("--record requires --candidate-id, --arm, --success and --selection-probability")
            return record_result(a.output, a.candidate_id, a.arm, a.success, a.selection_probability)
        return allocation_report(a.output)
    if a.command == "dependency-evaluate":
        from .dependency_evaluation import freeze_evaluation, report_evaluation

        if a.freeze:
            if not a.cohort or not a.methods:
                raise ValueError("--freeze requires --cohort and --methods")
            return freeze_evaluation(a.cohort, a.methods, a.output, a.seed)
        return report_evaluation(a.output, a.results)
    if a.command == "dependency-release":
        from .dependency_release import create_release_manifest, verify_release_manifest

        if a.verify:
            return verify_release_manifest(a.verify, a.root)
        if not a.output or not a.files:
            raise ValueError("Manifest creation requires --output and at least one file")
        return create_release_manifest(a.root, a.files, a.output)
    if a.command == "suite":
        from .suite import create_suite, report_suite, run_suite

        if a.retry_failed and not a.resume:
            raise ValueError("--retry-failed requires --resume")
        if a.report:
            return report_suite(a.output)
        if not a.resume:
            create_suite(a.config, a.output)
        if a.execute or a.resume:
            return run_suite(a.output, a.retry_failed)
        return None
    if a.command == "diagnose-run":
        from .diagnostics import diagnose_run

        return diagnose_run(a.directory, a.artifact)
    if a.command == "compare":
        from .comparison import create_plan, report_comparison, run_comparison

        if a.retry_failed and not a.resume:
            raise ValueError("--retry-failed requires --resume")
        if (a.resume or a.report) and (a.models or a.sources or a.limit or a.all_tasks):
            raise ValueError("Existing plans are frozen; use a new output for different selections")
        if a.report:
            report_comparison(a.output)
        elif a.resume:
            run_comparison(a.output, a.retry_failed)
        else:
            create_plan(a.config, a.output, a.limit, a.all_tasks, a.models, a.sources)
            if a.execute:
                run_comparison(a.output)
        return None
    if a.command == "doctor":
        return doctor(a.config, a.check_models)
    if a.command == "data":
        from .data import download, prepare

        return (
            download(a.manifest, a.sources, a.output, a.limit)
            if a.action == "download"
            else prepare(a.manifest, a.raw, a.output, a.seed, a.research_pool)
        )
    if a.command == "collect":
        from .config import load_config
        from .runtime import collect

        config = load_config(a.config, a.override)
        if a.policy:
            config.run.policy = a.policy
        if a.budget is not None:
            config.run.verification_budget = a.budget
        if a.tuning:
            from .data import load_tasks
            from .replay import load_tuning

            if not a.artifact:
                raise ValueError("Online tuning requires its matching calibration artifact")
            tuning = load_tuning(a.tuning, a.artifact)
            if any(
                t.group_id in tuning["fit_groups"]
                for t, _ in load_tasks(a.tasks, a.split, a.source, a.limit)
            ):
                raise ValueError("Online evaluation overlaps validation tuning groups")
            key = f"{config.run.policy}:{config.run.verification_budget:g}"
            if key not in tuning["thresholds"]:
                raise ValueError(f"No validation threshold for {key}")
            config.run.threshold = tuning["thresholds"][key]
            config.run.dynamic_lambda = tuning["dynamic_lambda"]
            config.seed = tuning["seed"]
        return collect(
            a.tasks,
            config,
            a.output,
            a.split,
            a.source,
            a.limit,
            a.artifact,
            a.critic_dir,
            a.images,
        )
    if a.command == "store":
        from .store import export_ledger, verify_export

        if a.action == "export":
            return export_ledger(a.database, a.output, a.encrypt_env)
        if a.action == "verify":
            return verify_export(a.directory)
        from cryptography.fernet import Fernet

        if Path(a.output).exists():
            raise ValueError("Decryption output already exists")
        key = os.environ.get(a.key_env)
        if not key:
            raise ValueError(f"Missing encryption key in {a.key_env}")
        Path(a.output).write_bytes(Fernet(key.encode()).decrypt(Path(a.input).read_bytes()))
        return {"decrypted": a.output}
    if a.command == "labels":
        from .labels import annotation_queue, apply_annotations

        return (
            annotation_queue(a.records, a.output)
            if a.action == "queue"
            else apply_annotations(a.records, a.annotations, a.output)
        )
    if a.command == "critic":
        from .critic import score_records, train_linear, train_lora

        if a.action == "train-linear":
            return train_linear(a.records, a.output, a.scope, a.seed)
        if a.action == "train-lora":
            return train_lora(
                a.records,
                a.model_path,
                a.output,
                a.scope,
                a.epochs,
                a.batch_size,
                a.accumulation,
                a.max_length,
                a.seed,
            )
        return score_records(a.records, a.critic_dir, a.output)
    if a.command == "calibrate":
        from .calibration import fit_artifact

        return fit_artifact(a.records, a.output, a.scope, a.min_class_samples)
    if a.command == "validate-calibration":
        from .calibration import assess_calibration

        return assess_calibration(a.records, a.artifact, a.output, a.split)
    if a.command in {"tune", "replay"}:
        from .replay import sweep, tune

        if a.command == "tune":
            return tune(
                a.records, a.artifact, a.output, a.budgets, a.scope, a.seed, a.dynamic_lambda
            )
        return sweep(a.records, a.artifact, a.tuning, a.output, a.budgets, a.split, a.scope, a.seed)
    if a.command == "report":
        from .report import frontier_report

        return frontier_report(a.directory)
    if a.command == "online-report":
        from .report import online_report

        return online_report(a.summaries, a.output, a.swe_report)
    if a.command == "recovery-report":
        from .report import recovery_comparison

        return recovery_comparison(a.checkpoint, a.restart, a.output)
    if a.command == "swe":
        from .swe import build_images, evaluate_swe, image_map, pull_images

        if a.action == "image-map":
            return image_map(
                a.tasks,
                a.output,
                None if a.split == "all" else a.split,
                a.source,
                a.limit,
                a.namespace,
                a.arch,
            )
        if a.action == "pull-images":
            return pull_images(a.mapping)
        if a.action == "build-images":
            return build_images(a.dataset, a.workers, a.arch)
        return evaluate_swe(a.dataset, a.predictions, a.run_id, a.workers, a.execute, a.namespace)
    raise ValueError("Unknown command")


def main():
    a = parser().parse_args()
    try:
        if getattr(a, "limit", None) is not None and a.limit < 1:
            raise ValueError("--limit must be positive")
        result = dispatch(a)
        if result is not None:
            print(canonical(result).decode())
    except (
        ValueError,
        RuntimeError,
        OSError,
        ImportError,
        httpx.HTTPError,
        subprocess.SubprocessError,
    ) as e:
        print(f"VERITAS: {e}", file=sys.stderr)
        if os.environ.get("VERITAS_DEBUG"):
            raise
        raise SystemExit(2) from e
