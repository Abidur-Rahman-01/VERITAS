"""Resumable paired local-model comparison; missing grades/costs are never successes."""

import csv
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import httpx
import yaml
from pydantic import Field

from .calibration import wilson
from .config import Config, ModelConfig, load_config
from .data import load_tasks
from .io import digest, file_hash, read_jsonl, write_json, write_jsonl
from .sanitize import redact
from .schema import StrictModel


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
        "version": 1,
        "implementation_hashes": {
            name: file_hash(Path(__file__).with_name(name))
            for name in ["runtime.py", "models.py", "comparison.py", "contracts.py", "labels.py"]
        },
        "spec": spec.model_dump(mode="json"),
        "base_config": base.model_dump(mode="json"),
        "models": inventory,
        "excluded_models": excluded,
        "sources": source_rows,
        "tasks_manifest_sha256": file_hash(task_dir / "manifest.json"),
        "image_map_hashes": {
            source: file_hash(Path(o.images))
            for source, o in spec.swe.items()
            if o.images and Path(o.images).is_file()
        },
        "jobs": len(chosen) * len(inventory),
        "protocol": "Same tasks, no optional verification/critic; deterministic floor retained",
        "holdout_tasks": sum(a["split"] == "test" for _, a in chosen),
        "note": "Exploratory comparison, not final research evidence or official full-set scores",
    }
    plan["plan_id"] = digest(plan)
    write_json(output / "plan.json", plan)
    print(f"Plan: {len(inventory)} models x {len(chosen)} tasks = {plan['jobs']} runs", flush=True)
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
    return plan


def job_key(model, task_id):
    return digest([model, task_id])[:24]


def grade_swe(task, collection, options):
    """Use the real harness. Missing reports are never counted as passes."""
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
            config = Config.model_validate(plan["base_config"])
            config.model = spec.server.model_copy(update={"name": model["name"]})
            for dataset in plan["sources"]:
                for task_id in dataset["task_ids"]:
                    task, assignment = tasks[task_id]
                    directory = output / "jobs" / job_key(model["name"], task_id)
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
                                raise ValueError("SWE image map missing; see docs/COMPARISON.md")
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
                            selected_tasks=[(task, assignment)],
                        )
                        summary = result["summary"] = next(
                            read_jsonl(attempt / "collection" / "summaries.jsonl")
                        )
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
        for source in plan["sources"]:
            results = []
            for task_id in source["task_ids"]:
                path = output / "jobs" / job_key(model["name"], task_id) / "result.json"
                if path.exists():
                    result = json.loads(path.read_text())
                    if (result["model"], result["task_id"]) != (model["name"], task_id):
                        raise ValueError("Comparison result identity mismatch")
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
                    "seconds_per_task": sum(r["wall_seconds_including_grading"] for r in results)
                    / selected
                    if complete
                    else None,
                    "metric": sorted({r["metric"] for r in results}),
                    "has_retries": any(
                        len(list((output / "jobs" / job_key(model["name"], t)).glob("attempt-*")))
                        > 1
                        for t in source["task_ids"]
                    ),
                }
            )
    return rows


def render_table(rows):
    headers = [
        "Model",
        "Dataset",
        "Graded/N",
        "Correct",
        "Score %",
        "Tokens/task",
        "Sec/task",
        "Err/Block/Pend",
    ]
    table = []
    for r in rows:
        table.append(
            [
                r["model"],
                r["dataset"],
                f"{r['graded']}/{r['selected']}",
                str(r["successes"]),
                f"{100 * r['success_rate']:.1f}" if r["success_rate"] is not None else "N/A",
                f"{r['tokens_per_task']:.0f}" if r["tokens_per_task"] is not None else "N/A",
                f"{r['seconds_per_task']:.1f}" if r["seconds_per_task"] is not None else "N/A",
                f"{r['errors']}/{r['blocked']}/{r['pending']}",
            ]
        )
    widths = [max(len(str(r[i])) for r in [headers, *table]) for i in range(len(headers))]
    line = "-+-".join("-" * width for width in widths)
    return "\n".join(
        [" | ".join(h.ljust(w) for h, w in zip(headers, widths)), line]
        + [" | ".join(v.ljust(w) for v, w in zip(row, widths)) for row in table]
    )


def report_comparison(output):
    output = Path(output)
    plan = read_plan(output)
    rows = comparison_rows(output, plan)
    write_json(output / "comparison.json", rows)
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
