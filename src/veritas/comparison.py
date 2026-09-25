"""Resumable paired local-model comparison; missing grades/costs are never successes."""

import csv
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import httpx
import yaml
from pydantic import Field

from .calibration import load_artifact, wilson
from .config import Config, ModelConfig, load_config
from .controller import ONLINE_POLICIES
from .data import load_tasks
from .io import digest, file_hash, read_jsonl, write_json, write_jsonl
from .provenance import critic_identity, verifier_identity
from .replay import load_tuning
from .sanitize import redact
from .schema import StrictModel

SCORED_POLICIES = {"confidence", "error_impact", "bavar_style", "rcvov"}


class CalibrationOptions(StrictModel):
    artifact: str
    tuning: str


class SWEOptions(StrictModel):
    images: str | None = None
    python: str | None = None
    namespace: str = "swebench"
    timeout_seconds: int = Field(default=1800, gt=0)


class ComparisonConfig(StrictModel):
    tasks: str = "data/prepared"
    base_config: str = "configs/experiment.yaml"
    server: ModelConfig = Field(
        default_factory=lambda: ModelConfig(backend="ollama", base_url="http://127.0.0.1:11434")
    )
    models: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    split: str | None = None
    limit: int | None = Field(default=5, gt=0)
    seed: int = 42
    swe: dict[str, SWEOptions] = Field(default_factory=dict)
    policies: list[str] = Field(default_factory=lambda: ["never"])
    verification_budget: float = Field(default=0.2, ge=0)
    calibration: dict[str, CalibrationOptions] = Field(default_factory=dict)
    critic_dir: str | None = None
    overrides: dict[str, str] = Field(default_factory=dict)


def discover_models(server, names=None):
    """Metadata requests only; Transformers uses explicitly supplied local paths."""
    names = names or []
    if server.backend == "transformers":
        if not names:
            raise ValueError("Transformers comparison requires explicit local model paths")
        return [{"name": str(Path(n).resolve()), "digest": None} for n in names], []
    headers = {}
    key = os.environ.get(server.api_key_env)
    if key:
        headers["Authorization"] = "Bearer " + key
    with httpx.Client(timeout=30, headers=headers) as client:
        base = server.base_url.rstrip("/")
        response = client.get(base + ("/api/tags" if server.backend == "ollama" else "/models"))
        response.raise_for_status()
        payload = response.json()
        inventory = {
            r["name"] if server.backend == "ollama" else r["id"]: r
            for r in payload["models" if server.backend == "ollama" else "data"]
        }
        missing = set(names) - inventory.keys()
        if missing:
            raise ValueError(f"Models are not installed/served: {sorted(missing)}")
        selected, excluded = [], []
        for name in sorted(names or inventory):
            capabilities = None
            if server.backend == "ollama":
                response = client.post(base + "/api/show", json={"model": name})
                response.raise_for_status()
                capabilities = response.json().get("capabilities")
            if capabilities is not None and "completion" not in capabilities:
                excluded.append({"name": name, "reason": "No completion capability"})
                continue
            selected.append(
                {
                    "name": name,
                    "digest": inventory[name].get("digest"),
                    "capabilities": capabilities,
                }
            )
    if not selected:
        raise ValueError("No text generation models available")
    return selected, excluded


def create_plan(config_path, output, limit=None, all_tasks=False, models=None, sources=None):
    output = Path(output).resolve()
    if (output / "plan.json").exists():
        raise ValueError("Plan already exists. Use --resume or choose another output directory")
    spec = ComparisonConfig.model_validate(yaml.safe_load(Path(config_path).read_text()))
    if limit is not None:
        spec.limit = limit
    if all_tasks:
        spec.limit = None
    if models:
        spec.models = models
    if sources:
        spec.sources = sources
    if spec.split not in {None, "dev", "calib", "val", "test", "backbone"}:
        raise ValueError("Invalid research split")
    if (
        not spec.policies
        or len(set(spec.policies)) != len(spec.policies)
        or set(spec.policies) - set(ONLINE_POLICIES)
    ):
        raise ValueError("Policies must be a unique nonempty selection of supported policies")
    inventory, excluded = discover_models(spec.server, spec.models)
    base = load_config(spec.base_config)
    base.run.policy = "never"
    base.run.audit_all = False
    base.run.allow_uncalibrated = True
    base.run.score_critic = False
    base.run.verification_budget = 0
    base.seed = spec.seed
    source_manifest = json.loads((Path(spec.tasks) / "manifest.json").read_text())
    requested = spec.sources or sorted(source_manifest["sources"])
    if len(set(requested)) != len(requested):
        raise ValueError("Duplicate dataset source names")
    if set(requested) - source_manifest["sources"].keys():
        raise ValueError("Requested source missing from prepared provenance manifest")
    grouped = defaultdict(list)
    for task, assignment in load_tasks(spec.tasks, spec.split):
        if task.source in requested:
            grouped[task.source].append((task, assignment))
    chosen, source_rows = [], []
    for source in requested:
        pool = sorted(grouped[source], key=lambda pair: digest([spec.seed, pair[0].task_id]))
        selection = pool if spec.limit is None else pool[: spec.limit]
        chosen.extend(selection)
        source_rows.append(
            {
                "source": source,
                "available": len(pool),
                "selected": len(selection),
                "task_ids": [t.task_id for t, _ in selection],
            }
        )
    if not chosen:
        raise ValueError("No tasks selected")
    calibrations, calibration_hashes = {}, {}
    for source in requested:
        options = spec.calibration.get(source)
        if not options and set(spec.policies) & SCORED_POLICIES:
            raise ValueError(
                f"Scored policies need empirical calibration and validation tuning for {source}"
            )
        if options:
            options.artifact, options.tuning = (
                str(Path(options.artifact).resolve()),
                str(Path(options.tuning).resolve()),
            )
            artifact = load_artifact(options.artifact)
            tuning = load_tuning(options.tuning, options.artifact)
            if tuning["seed"] != spec.seed:
                raise ValueError("Comparison seed must match validation tuning seed")
            fitted = set(artifact["fit_groups"]) | set(tuning["fit_groups"])
            if any(t.group_id in fitted for t, _ in chosen):
                raise ValueError("Comparison tasks overlap calibration/tuning groups")
            calibrations[source] = tuning
            for path in (options.artifact, options.tuning):
                calibration_hashes[path] = file_hash(Path(path))
                data = json.loads(Path(path).read_text())
                evidence = Path(path).parent / data["evidence_file"]
                calibration_hashes[str(evidence)] = file_hash(evidence)
            for policy in spec.policies:
                if policy == "graph":
                    continue
                if f"{policy}:{spec.verification_budget:g}" not in tuning["thresholds"]:
                    raise ValueError(
                        f"Budget/policy {policy}:{spec.verification_budget:g} was not tuned"
                    )
    if spec.critic_dir:
        spec.critic_dir = str(Path(spec.critic_dir).resolve())
        for path in Path(spec.critic_dir).rglob("*"):
            if path.is_file():
                calibration_hashes[str(path)] = file_hash(path)
    source_configs = {
        source: load_config(spec.base_config, spec.overrides.get(source)).model_dump(mode="json")
        for source in requested
    }
    trained = None
    if spec.critic_dir:
        # Planning reads metadata/hashes only, including for a large LoRA critic.
        trained = SimpleNamespace(
            metadata=json.loads((Path(spec.critic_dir) / "metadata.json").read_text())
        )
        if set(spec.policies) & SCORED_POLICIES and any(
            t.group_id in trained.metadata.get("fit_groups", []) for t, _ in chosen
        ):
            raise ValueError("Comparison tasks overlap critic training groups")
    for source, options in spec.calibration.items():
        if source not in source_configs:
            continue
        config = Config.model_validate(source_configs[source])
        artifact = load_artifact(options.artifact)
        if artifact["critic_id"] != critic_identity(config, trained) or artifact[
            "verifier_id"
        ] != verifier_identity(config):
            raise ValueError(
                f"Calibration identity differs from current code/config for {source}; recollect and refit"
            )
    auxiliary_models = []
    seen_aux = set()
    for source_config in source_configs.values():
        config = Config.model_validate(source_config)
        uses_verifier = bool(set(spec.policies) - {"never", "graph"}) or (
            "graph" in spec.policies
            and config.graph.semantic_final_review
            and config.graph.max_semantic_calls > 0
        )
        roles = [config.verifier] if uses_verifier else []
        if set(spec.policies) & SCORED_POLICIES and not spec.critic_dir:
            roles.append(config.critic)
        for model_config in roles:
            identity = digest(model_config.model_dump(mode="json"))
            if identity in seen_aux:
                continue
            seen_aux.add(identity)
            installed, _ = discover_models(model_config, [model_config.name])
            auxiliary_models.append(
                {"config": model_config.model_dump(mode="json"), "models": installed}
            )
    task_dir = output / "tasks"
    write_jsonl(task_dir / "tasks.jsonl", (t.model_dump(mode="json") for t, _ in chosen))
    write_json(task_dir / "splits.json", {t.group_id: a for t, a in chosen})
    write_json(
        task_dir / "manifest.json",
        {
            "tasks_sha256": file_hash(task_dir / "tasks.jsonl"),
            "splits_sha256": file_hash(task_dir / "splits.json"),
            "parent_manifest_sha256": file_hash(Path(spec.tasks) / "manifest.json"),
            "sources": source_manifest["sources"],
            "note": "Original records; frozen paired selection and original research assignments",
        },
    )
    for options in spec.swe.values():
        if options.images:
            options.images = str(Path(options.images).resolve())
        if options.python:
            options.python = str(Path(options.python).resolve())
    plan = {
        "version": 2,
        "implementation_hashes": {
            name: file_hash(Path(__file__).with_name(name))
            for name in sorted(p.name for p in Path(__file__).parent.glob("*.py"))
        },
        "spec": spec.model_dump(mode="json"),
        "base_config": base.model_dump(mode="json"),
        "source_configs": source_configs,
        "calibration_hashes": calibration_hashes,
        "tuning": calibrations,
        "models": inventory,
        "auxiliary_models": auxiliary_models,
        "excluded_models": excluded,
        "sources": source_rows,
        "tasks_manifest_sha256": file_hash(task_dir / "manifest.json"),
        "image_map_hashes": {
            source: file_hash(Path(o.images))
            for source, o in spec.swe.items()
            if o.images and Path(o.images).is_file()
        },
        "jobs": len(chosen) * len(inventory) * len(spec.policies),
        "protocol": "Paired tasks and actor settings; shared verification cap; critic only for score-based policies; all attempts retained",
        "holdout_tasks": sum(a["split"] == "test" for _, a in chosen),
        "note": "Exploratory comparison, not final research evidence or official full-set scores",
    }
    plan["plan_id"] = digest(plan)
    write_json(output / "plan.json", plan)
    print(
        f"Plan: {len(inventory)} models x {len(spec.policies)} policies x {len(chosen)} tasks = {plan['jobs']} runs",
        flush=True,
    )
    print(f"Reserved test tasks included: {plan['holdout_tasks']}. No models invoked.", flush=True)
    for row in source_rows:
        print(f"  {row['source']}: {row['selected']}/{row['available']} prepared tasks")
    return plan


def read_plan(output):
    output = Path(output)
    plan = json.loads((output / "plan.json").read_text())
    expected = dict(plan)
    identity = expected.pop("plan_id")
    if digest(expected) != identity:
        raise ValueError("Comparison plan changed; create a new plan")
    if file_hash(output / "tasks" / "manifest.json") != plan["tasks_manifest_sha256"]:
        raise ValueError("Frozen task manifest changed")
    for source, sha in plan["image_map_hashes"].items():
        path = plan["spec"]["swe"][source]["images"]
        if file_hash(Path(path)) != sha:
            raise ValueError(f"Image mapping changed for {source}; use a new plan")
    for path, sha in plan.get("calibration_hashes", {}).items():
        if file_hash(Path(path)) != sha:
            raise ValueError("Calibration/tuning/critic changed since planning; create a new plan")
    return plan


def job_key(model, task_id, policy="never"):
    # Preserve legacy never-only job IDs so old reports remain readable.
    return digest([model, task_id] if policy == "never" else [model, task_id, policy])[:24]


def grade_swe(task, collection, options):
    """Use the real harness. Missing reports are never counted as passes."""
    from .swe import require_supported_host

    require_supported_host()
    predictions = list(read_jsonl(collection / "predictions.jsonl"))
    if len(predictions) != 1:
        raise ValueError("Expected one SWE prediction")
    if not predictions[0]["model_patch"].strip():
        return False, "empty_patch"
    grading = collection / "grading"
    grading.mkdir(exist_ok=True)
    dataset = grading / "task.jsonl"
    write_jsonl(dataset, [task.private])
    # Avoid slashes/colons in report filenames on Windows.
    predictions[0]["model_name_or_path"] = "comparison"
    prediction_path = grading / "prediction.jsonl"
    write_jsonl(prediction_path, predictions)
    command = [
        options.python or sys.executable,
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        str(dataset),
        "--predictions_path",
        str(prediction_path),
        "--run_id",
        "grade",
        "--namespace",
        options.namespace or "none",
        "--max_workers",
        "1",
    ]
    with (grading / "harness.log").open("w", encoding="utf-8") as log:
        subprocess.run(
            command,
            cwd=grading,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=options.timeout_seconds,
        )
    report_path = grading / "comparison.grade.json"
    if not report_path.exists():
        raise ValueError("SWE grader report missing; inspect harness.log")
    report = json.loads(report_path.read_text())
    identity = task.private["instance_id"]
    if identity in report.get("resolved_ids", []):
        return True, "official_swe_tests"
    if identity in report.get("unresolved_ids", []):
        return False, "official_swe_tests"
    raise ValueError("Task ungraded by SWE harness (environment/test execution error)")


def run_comparison(output, retry_failed=False):
    from .runtime import collect

    output = Path(output).resolve()
    plan = read_plan(output)
    spec = ComparisonConfig.model_validate(plan["spec"])
    current, _ = discover_models(spec.server, [m["name"] for m in plan["models"]])
    if {(m["name"], m["digest"]) for m in current} != {
        (m["name"], m["digest"]) for m in plan["models"]
    }:
        raise ValueError("Installed model digests changed; create a new plan")
    for auxiliary in plan.get("auxiliary_models", []):
        config = ModelConfig.model_validate(auxiliary["config"])
        installed, _ = discover_models(config, [config.name])
        if installed != auxiliary["models"]:
            raise ValueError("Critic/verifier model metadata changed; create a new plan")
    tasks = {t.task_id: (t, a) for t, a in load_tasks(output / "tasks")}
    for name, expected in plan.get("implementation_hashes", {}).items():
        if file_hash(Path(__file__).with_name(name)) != expected:
            raise ValueError("Runner code changed since planning; create a new comparison plan")
    lock = output / ".running"
    try:
        handle = lock.open("x")
    except FileExistsError as e:
        raise ValueError(
            "Comparison locked. If its process ended, remove .running before resume"
        ) from e
    handle.write(str(os.getpid()))
    handle.close()
    try:
        resource_path = output / "resources.json"
        resources = json.loads(resource_path.read_text()) if resource_path.exists() else {}
        for source, options in spec.swe.items():
            if options.images and Path(options.images).is_file():
                sha = file_hash(Path(options.images))
                if source in resources and resources[source] != sha:
                    raise ValueError(f"Executed image map changed for {source}; create a new plan")
                resources[source] = sha
        write_json(resource_path, resources)
        for model in plan["models"]:
            for dataset in plan["sources"]:
                for task_id in dataset["task_ids"]:
                    policies = sorted(spec.policies, key=lambda p: digest([spec.seed, task_id, p]))
                    for policy in policies:
                        task, assignment = tasks[task_id]
                        config = Config.model_validate(
                            plan.get("source_configs", {}).get(task.source, plan["base_config"])
                        )
                        config.model = spec.server.model_copy(
                            update={
                                "name": model["name"],
                                "max_tokens": config.model.max_tokens,
                                "temperature": config.model.temperature,
                                "prompt_style": config.model.prompt_style,
                                "timeout_seconds": config.model.timeout_seconds,
                            }
                        )
                        config.seed = spec.seed
                        config.run.policy, config.run.audit_all = policy, False
                        config.run.score_critic = policy in SCORED_POLICIES
                        config.run.allow_uncalibrated = policy not in SCORED_POLICIES
                        config.run.verification_budget = spec.verification_budget
                        config.run.dynamic_lambda = 0.0
                        calibration = spec.calibration.get(task.source)
                        if calibration and policy != "graph":
                            tuning = plan["tuning"][task.source]
                            config.run.threshold = tuning["thresholds"][
                                f"{policy}:{spec.verification_budget:g}"
                            ]
                            config.run.dynamic_lambda = tuning["dynamic_lambda"]
                        directory = output / "jobs" / job_key(model["name"], task_id, policy)
                        result_file = directory / "result.json"
                        if result_file.exists():
                            prior = json.loads(result_file.read_text())
                            if prior["status"] == "done" or not retry_failed:
                                continue
                        directory.mkdir(parents=True, exist_ok=True)
                        attempt = directory / f"attempt-{time.time_ns()}"
                        attempt.mkdir()
                        result = {
                            "model": model["name"],
                            "policy": policy,
                            "actions": None,
                            "source": task.source,
                            "task_id": task_id,
                            "status": "error",
                            "success": None,
                            "summary": None,
                            "metric": "numeric_answer"
                            if task.kind == "gsm8k"
                            else "exact_string"
                            if task.kind == "math"
                            else "official_swe_tests",
                            "attempt": str(attempt.relative_to(output)),
                            "error": None,
                        }
                        start = time.monotonic()
                        try:
                            options = spec.swe.get(task.source, SWEOptions())
                            if task.kind == "swe":
                                if not options.images or not Path(options.images).is_file():
                                    result["status"] = "blocked"
                                    raise ValueError(
                                        "SWE image map missing; see docs/COMPARISON.md"
                                    )
                                mapping = json.loads(Path(options.images).read_text())
                                if task.private["instance_id"] not in mapping:
                                    result["status"] = "blocked"
                                    raise ValueError("Selected task has no prepared image mapping")
                                if options.python and not Path(options.python).is_file():
                                    result["status"] = "blocked"
                                    raise ValueError("Configured SWE harness Python is missing")
                            collect(
                                output / "tasks",
                                config,
                                attempt / "collection",
                                images=options.images,
                                artifact=calibration.artifact
                                if calibration and config.run.score_critic
                                else None,
                                critic_dir=spec.critic_dir if config.run.score_critic else None,
                                selected_tasks=[(task, assignment)],
                            )
                            summary = result["summary"] = next(
                                read_jsonl(attempt / "collection" / "summaries.jsonl")
                            )
                            ledger = attempt / "collection" / "events.sqlite"
                            if ledger.exists():
                                from .report import action_metrics
                                from .store import EventStore

                                store = EventStore(ledger)
                                try:
                                    result["actions"] = action_metrics(
                                        r.model_dump(mode="json") for r in store.records()
                                    )
                                finally:
                                    store.close()
                            success = summary["task_success"]
                            if task.kind == "swe":
                                success, result["metric"] = grade_swe(
                                    task, attempt / "collection", options
                                )
                            result["success"], result["status"] = success, "done"
                        except Exception as e:
                            result["error"] = redact(f"{type(e).__name__}: {e}")[:3000]
                            print(
                                f"  {model['name']} / {task_id}: {result['status']} - {result['error']}",
                                flush=True,
                            )
                        result["wall_seconds_including_grading"] = time.monotonic() - start
                        write_json(attempt / "result.json", result)
                        write_json(result_file, result)
                report_comparison(output)
    finally:
        lock.unlink(missing_ok=True)
    return report_comparison(output)


def comparison_rows(output, plan):
    output = Path(output)
    rows = []
    for model in plan["models"]:
        for policy in plan["spec"].get("policies", ["never"]):
            for source in plan["sources"]:
                results = []
                for task_id in source["task_ids"]:
                    path = output / "jobs" / job_key(model["name"], task_id, policy) / "result.json"
                    if path.exists():
                        result = json.loads(path.read_text())
                        if (result["model"], result["task_id"]) != (model["name"], task_id):
                            raise ValueError("Comparison result identity mismatch")
                        if result.get("policy", "never") != policy:
                            raise ValueError("Comparison result policy mismatch")
                        results.append(result)
                done = [r for r in results if r["status"] == "done" and r["success"] is not None]
                summaries = [r["summary"] for r in results if r["summary"] is not None]
                selected = source["selected"]
                complete = selected > 0 and len(done) == selected
                tokens = sum(s["total_online_tokens"] + s["audit_tokens"] for s in summaries)
                measured = complete and all(s["token_usage_complete"] for s in summaries)
                successes = sum(r["success"] is True for r in done)
                rows.append(
                    {
                        "model": model["name"],
                        "policy": policy,
                        "dataset": source["source"],
                        "selected": selected,
                        "graded": len(done),
                        "successes": successes,
                        "success_rate": successes / selected if complete else None,
                        "success_ci95": wilson(successes, selected) if complete else None,
                        "errors": sum(r["status"] == "error" for r in results),
                        "blocked": sum(r["status"] == "blocked" for r in results),
                        "pending": selected - len(results),
                        "complete": complete,
                        "known_tokens": tokens,
                        "token_usage_complete": measured,
                        "tokens_per_task": tokens / selected if measured else None,
                        "tokens_per_success": tokens / successes
                        if measured and successes
                        else None,
                        "graph_model_calls": sum(s.get("graph_model_calls", 0) for s in summaries),
                        "graph_cache_hits": sum(s.get("graph_cache_hits", 0) for s in summaries),
                        "advisory_reviews": sum(
                            (r.get("actions") or {}).get("advisory_reviews", 0) for r in results
                        ),
                        "seconds_per_task": sum(
                            r["wall_seconds_including_grading"] for r in results
                        )
                        / selected
                        if complete
                        else None,
                        "metric": sorted({r["metric"] for r in results}),
                        "false_rejections": sum(r["actions"]["false_rejections"] for r in results)
                        if complete
                        and all(
                            r.get("actions") and r["actions"]["false_rejections"] is not None
                            for r in results
                        )
                        else None,
                        "errors_caught": sum(r["actions"]["errors_caught"] for r in results)
                        if complete
                        and all(
                            r.get("actions") and r["actions"]["errors_caught"] is not None
                            for r in results
                        )
                        else None,
                        "critic_errors": sum(
                            (r.get("actions") or {}).get("critic_errors", 0) for r in results
                        ),
                        "fallback_actions": sum(
                            (r.get("actions") or {}).get("fallback_actions", 0) for r in results
                        ),
                        "semantic_label_coverage": (
                            sum(r["actions"]["semantic_labeled_actions"] for r in results)
                            / sum(r["actions"]["eligible_actions"] for r in results)
                        )
                        if complete
                        and all(r.get("actions") for r in results)
                        and sum(r["actions"]["eligible_actions"] for r in results)
                        else None,
                        "has_retries": any(
                            len(
                                list(
                                    (output / "jobs" / job_key(model["name"], t, policy)).glob(
                                        "attempt-*"
                                    )
                                )
                            )
                            > 1
                            for t in source["task_ids"]
                        ),
                    }
                )
    return rows


def render_table(rows):
    headers = [
        "Model",
        "Policy",
        "Dataset",
        "Graded/N",
        "Correct",
        "Score %",
        "Tokens/task",
        "Tokens/solve",
        "Sec/task",
        "Err/Block/Pend",
        "False rej.",
        "Caught",
        "Labels %",
    ]
    table = []
    for r in rows:
        table.append(
            [
                r["model"],
                r.get("policy", "never"),
                r["dataset"],
                f"{r['graded']}/{r['selected']}",
                str(r["successes"]),
                f"{100 * r['success_rate']:.1f}" if r["success_rate"] is not None else "N/A",
                f"{r['tokens_per_task']:.0f}" if r["tokens_per_task"] is not None else "N/A",
                f"{r['tokens_per_success']:.0f}"
                if r.get("tokens_per_success") is not None
                else "N/A",
                f"{r['seconds_per_task']:.1f}" if r["seconds_per_task"] is not None else "N/A",
                f"{r['errors']}/{r['blocked']}/{r['pending']}",
                str(r["false_rejections"]) if r.get("false_rejections") is not None else "N/A",
                str(r["errors_caught"]) if r.get("errors_caught") is not None else "N/A",
                f"{100 * r['semantic_label_coverage']:.1f}"
                if r.get("semantic_label_coverage") is not None
                else "N/A",
            ]
        )
    widths = [max(len(str(r[i])) for r in [headers, *table]) for i in range(len(headers))]
    line = "-+-".join("-" * width for width in widths)
    return "\n".join(
        [" | ".join(h.ljust(w) for h, w in zip(headers, widths)), line]
        + [" | ".join(v.ljust(w) for v, w in zip(row, widths)) for row in table]
    )


def policy_effects(output, plan):
    """Paired uncertainty from complete task sets; partial results cannot establish gains."""
    from .replay import paired_bootstrap

    effects = []
    policies = plan["spec"].get("policies", ["never"])
    primary = "graph" if "graph" in policies else "rcvov"
    if primary not in policies:
        return effects
    for model in plan["models"]:
        for source in plan["sources"]:
            groups = {}
            for policy in policies:
                results = []
                for task_id in source["task_ids"]:
                    path = (
                        Path(output)
                        / "jobs"
                        / job_key(model["name"], task_id, policy)
                        / "result.json"
                    )
                    if not path.exists():
                        continue
                    r = json.loads(path.read_text())
                    if r["status"] == "done" and r["success"] is not None:
                        summary = r["summary"]
                        results.append(
                            {
                                "run_id": model["name"],
                                "task_id": task_id,
                                "group_id": task_id,
                                "success": int(r["success"]),
                                "tokens": summary["total_online_tokens"],
                                "measured": summary["token_usage_complete"],
                            }
                        )
                groups[policy] = results
            for baseline in policies:
                if baseline == primary:
                    continue
                left, right = groups[primary], groups[baseline]
                complete = source["selected"] > 0 and len(left) == len(right) == source["selected"]
                effects.append(
                    {
                        "model": model["name"],
                        "dataset": source["source"],
                        "baseline": baseline,
                        "policy": primary,
                        "complete": complete,
                        "selected": source["selected"],
                        "success_delta": paired_bootstrap(
                            left, right, "success", seed=plan["spec"]["seed"]
                        )
                        if complete
                        else None,
                        "tokens_delta": paired_bootstrap(
                            left, right, "tokens", seed=plan["spec"]["seed"]
                        )
                        if complete and all(r["measured"] for r in left + right)
                        else None,
                        "note": f"{primary} minus baseline, per task. Small pilots are descriptive; CIs do not correct multiple comparisons or systematic grading bias.",
                    }
                )
    return effects


def report_comparison(output):
    output = Path(output)
    plan = read_plan(output)
    rows = comparison_rows(output, plan)
    write_json(output / "comparison.json", rows)
    write_json(output / "policy_effects.json", policy_effects(output, plan))
    with (output / "comparison.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    table = render_table(rows)
    (output / "comparison.txt").write_text(table + "\n", encoding="utf-8")
    print(table, flush=True)
    print(
        "N/A = incomplete/ungraded. Costs cover latest attempts; retries remain in jobs/.\n"
        "Scores are per dataset; MATH uses exact-string grading. No cross-dataset overall rank.",
        flush=True,
    )
    return rows
