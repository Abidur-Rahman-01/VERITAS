"""Balanced four-arm dependency pilot scheduling and accounting.

This freezes matched task/arm/repetition jobs before execution. The current runner
executes the common runtime with opportunity observation enabled and records whether
A/B were reached; active optional-check intervention is intentionally recorded as
shadow observation until the intervention executor is wired into runtime branches.
"""

import csv
import json
import os
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from .config import Config, load_config
from .data import load_tasks
from .dependency_cohort import verify_cohort
from .io import digest, file_hash, read_jsonl, write_json, write_jsonl
from .sanitize import redact
from .schema import StrictModel

ARMS = ("00", "10", "01", "11")


class PilotConfig(StrictModel):
    cohort: str
    tasks: str = "data/prepared"
    base_config: str = "configs/experiment.yaml"
    partition: Literal["discovery", "confirmation"] = "discovery"
    limit: int | None = Field(default=None, gt=0)
    repetitions: int | None = Field(default=None, gt=0)
    order_seed: int | None = None
    images: dict[str, str] = Field(default_factory=dict)
    note: str = "balanced dependency pilot schedule"


def _resolved(row):
    eligibility = row["eligibility"]
    return eligibility.get("adjudication") or eligibility["reviews"][0] if "reviews" in eligibility else eligibility


def _identity(symbol, evidence):
    if "::" in symbol:
        return symbol
    return f"{evidence['path']}::{symbol}"


def create_pilot(config, output):
    output = Path(output).resolve()
    if (output / "pilot.json").exists():
        raise ValueError("Pilot already exists. Use --resume or choose another output directory")
    spec = PilotConfig.model_validate(yaml.safe_load(Path(config).read_text()))
    cohort_dir = Path(spec.cohort)
    verify_cohort(cohort_dir)
    protocol = json.loads((cohort_dir / "protocol.json").read_text())
    if tuple(protocol["arms"]) != ARMS:
        raise ValueError("Dependency pilot requires arms 00, 10, 01 and 11 in that order")
    repetitions = spec.repetitions or protocol["repetitions"]
    seeds = protocol["seeds"][:repetitions]
    if len(seeds) != repetitions:
        raise ValueError("Protocol does not provide enough repetition seeds")
    base = load_config(spec.base_config)
    if base.run.max_steps != protocol["max_steps"]:
        raise ValueError("Pilot config/protocol max_steps mismatch")
    if base.run.verification_budget != protocol["verification_budget"]:
        raise ValueError("Pilot config/protocol verification_budget mismatch")
    if base.run.verification_cost != protocol["verification_cost"]:
        raise ValueError("Pilot config/protocol verification_cost mismatch")
    cohort_rows = [
        row for row in read_jsonl(cohort_dir / "cohort.jsonl")
        if row["research_partition"] == spec.partition
    ]
    cohort_rows.sort(key=lambda row: digest([protocol["partition_seed"], row["task_id"]]))
    if spec.limit is not None:
        cohort_rows = cohort_rows[:spec.limit]
    if not cohort_rows:
        raise ValueError("No cohort tasks selected for pilot")
    task_map = {task.task_id: (task, assignment) for task, assignment in load_tasks(spec.tasks)}
    missing = [row["task_id"] for row in cohort_rows if row["task_id"] not in task_map]
    if missing:
        raise ValueError(f"Cohort tasks missing from prepared task source: {missing[:3]}")
    output.mkdir(parents=True, exist_ok=True)
    selected = []
    for row in cohort_rows:
        task, assignment = task_map[row["task_id"]]
        if task.kind != "swe":
            raise ValueError("Dependency pilot currently supports SWE tasks only")
        review = _resolved(row)
        selected.append({
            "task_id": task.task_id,
            "group_id": task.group_id,
            "source": task.source,
            "assignment": assignment,
            "target_identity": _identity(review["target_symbol"], review["target_evidence"]),
            "caller_identity": _identity(review["caller_symbol"], review["caller_evidence"]),
        })
    task_dir = output / "tasks"
    write_jsonl(task_dir / "tasks.jsonl", (task_map[row["task_id"]][0].model_dump(mode="json") for row in selected))
    write_json(task_dir / "splits.json", {row["group_id"]: row["assignment"] for row in selected})
    parent_manifest = json.loads((Path(spec.tasks) / "manifest.json").read_text())
    write_json(task_dir / "manifest.json", {
        "tasks_sha256": file_hash(task_dir / "tasks.jsonl"),
        "splits_sha256": file_hash(task_dir / "splits.json"),
        "parent_manifest_sha256": file_hash(Path(spec.tasks) / "manifest.json"),
        "sources": parent_manifest.get("sources", {}),
        "note": "Frozen dependency-pilot task subset with original private fields retained locally",
    })
    order_seed = protocol["partition_seed"] if spec.order_seed is None else spec.order_seed
    jobs = []
    for task in selected:
        for repetition, seed in enumerate(seeds):
            for arm in ARMS:
                job = {
                    "job_id": digest([task["task_id"], arm, repetition, seed])[:24],
                    "task_id": task["task_id"],
                    "group_id": task["group_id"],
                    "source": task["source"],
                    "arm": arm,
                    "repetition": repetition,
                    "seed": seed,
                    "target_identity": task["target_identity"],
                    "caller_identity": task["caller_identity"],
                }
                job["order_key"] = digest([order_seed, job["job_id"]])
                jobs.append(job)
    jobs.sort(key=lambda job: job["order_key"])
    plan = {
        "version": 1,
        "spec": spec.model_dump(mode="json"),
        "protocol": protocol,
        "base_config": base.model_dump(mode="json"),
        "cohort_manifest_sha256": file_hash(cohort_dir / "manifest.json"),
        "tasks_manifest_sha256": file_hash(task_dir / "manifest.json"),
        "implementation_hashes": {
            name: file_hash(Path(__file__).with_name(name))
            for name in ("dependency_pilot.py", "runtime.py", "opportunities.py", "state.py")
        },
        "selected_tasks": selected,
        "jobs": jobs,
        "job_count": len(jobs),
        "execution_order": [job["job_id"] for job in jobs],
        "opportunity_policy_execution": "shadow_trigger_detection_only",
        "note": "Complete four-arm schedule; active optional-check intervention is not yet executed by this runner",
    }
    plan["pilot_id"] = digest(plan)
    write_json(output / "pilot.json", plan)
    print(
        f"Pilot: {len(selected)} tasks x {len(ARMS)} arms x {repetitions} repetitions = {len(jobs)} scheduled runs",
        flush=True,
    )
    return plan


def read_pilot(output):
    output = Path(output)
    plan = json.loads((output / "pilot.json").read_text())
    expected = dict(plan)
    identity = expected.pop("pilot_id")
    if digest(expected) != identity:
        raise ValueError("Pilot plan changed; create a new pilot")
    if file_hash(output / "tasks" / "manifest.json") != plan["tasks_manifest_sha256"]:
        raise ValueError("Frozen pilot tasks changed")
    cohort = Path(plan["spec"]["cohort"])
    if file_hash(cohort / "manifest.json") != plan["cohort_manifest_sha256"]:
        raise ValueError("Frozen cohort changed; create a new pilot")
    for name, sha in plan["implementation_hashes"].items():
        if file_hash(Path(__file__).with_name(name)) != sha:
            raise ValueError("Pilot runner code changed since planning; create a new pilot")
    return plan


def _event_status(summary, name):
    return (
        summary.get("opportunity_observation", {})
        .get("events", {})
        .get(name, {})
        .get("status", "not_recorded")
    )


def _run_result_path(output, job):
    return Path(output) / "jobs" / job["job_id"] / "result.json"


def run_pilot(output, retry_failed=False):
    from .runtime import collect

    output = Path(output).resolve()
    plan = read_pilot(output)
    spec = PilotConfig.model_validate(plan["spec"])
    tasks = {task.task_id: (task, assignment) for task, assignment in load_tasks(output / "tasks")}
    lock = output / ".running"
    try:
        handle = lock.open("x")
    except FileExistsError as exc:
        raise ValueError("Pilot locked. If its process ended, remove .running before resume") from exc
    handle.write(str(os.getpid()))
    handle.close()
    try:
        for job in plan["jobs"]:
            result_file = _run_result_path(output, job)
            if result_file.exists():
                prior = json.loads(result_file.read_text())
                if prior["status"] == "done" or not retry_failed:
                    continue
            task, assignment = tasks[job["task_id"]]
            config = Config.model_validate(plan["base_config"])
            config.seed = job["seed"]
            config.run.policy = "never"
            config.run.audit_all = False
            config.run.score_critic = False
            config.run.allow_uncalibrated = True
            config.run.verification_budget = plan["protocol"]["verification_budget"]
            config.run.verification_cost = plan["protocol"]["verification_cost"]
            config.opportunities.target_identity = job["target_identity"]
            config.opportunities.caller_identity = job["caller_identity"]
            config.opportunities.mode = "shadow"
            directory = result_file.parent
            directory.mkdir(parents=True, exist_ok=True)
            attempt = directory / f"attempt-{time.time_ns()}"
            attempt.mkdir()
            result = {
                "job_id": job["job_id"],
                "task_id": job["task_id"],
                "group_id": job["group_id"],
                "source": job["source"],
                "arm": job["arm"],
                "repetition": job["repetition"],
                "seed": job["seed"],
                "status": "error",
                "success": None,
                "summary": None,
                "opportunities": None,
                "opportunity_policy_execution": plan["opportunity_policy_execution"],
                "attempt": str(attempt.relative_to(output)),
                "error": None,
            }
            start = time.monotonic()
            try:
                images = spec.images.get(task.source)
                collect(
                    output / "tasks",
                    config,
                    attempt / "collection",
                    images=images,
                    selected_tasks=[(task, assignment)],
                )
                summary = result["summary"] = next(read_jsonl(attempt / "collection" / "summaries.jsonl"))
                result["opportunities"] = summary.get("opportunity_observation")
                result["success"] = summary.get("task_success")
                result["status"] = "done"
            except Exception as exc:
                result["error"] = redact(f"{type(exc).__name__}: {exc}")[:3000]
            result["wall_seconds"] = time.monotonic() - start
            write_json(attempt / "result.json", result)
            write_json(result_file, result)
        return report_pilot(output)
    finally:
        lock.unlink(missing_ok=True)


def pilot_rows(output):
    output = Path(output)
    plan = read_pilot(output)
    grouped = defaultdict(list)
    for job in plan["jobs"]:
        path = _run_result_path(output, job)
        result = json.loads(path.read_text()) if path.exists() else None
        grouped[(job["arm"], job["source"])].append((job, result))
    rows = []
    for (arm, source), pairs in sorted(grouped.items()):
        results = [result for _, result in pairs if result]
        done = [result for result in results if result["status"] == "done"]
        summaries = [result["summary"] for result in done if result["summary"]]
        successes = sum(result["success"] is True for result in done)
        scheduled = len(pairs)
        complete = len(done) == scheduled
        rows.append({
            "arm": arm,
            "source": source,
            "scheduled": scheduled,
            "done": len(done),
            "errors": sum(result["status"] == "error" for result in results),
            "pending": scheduled - len(results),
            "complete": complete,
            "successes": successes,
            "success_rate": successes / scheduled if complete else None,
            "triggered_A": sum(_event_status(summary, "A") != "never_triggered" for summary in summaries),
            "triggered_B": sum(_event_status(summary, "B") != "never_triggered" for summary in summaries),
            "never_reached_B": scheduled - sum(_event_status(summary, "B") != "never_triggered" for summary in summaries),
            "known_tokens": sum(summary.get("total_online_tokens", 0) + summary.get("audit_tokens", 0) for summary in summaries),
            "token_usage_complete": complete and all(summary.get("token_usage_complete") for summary in summaries),
            "opportunity_policy_execution": plan["opportunity_policy_execution"],
        })
    return rows


def report_pilot(output):
    output = Path(output)
    rows = pilot_rows(output)
    write_json(output / "pilot-results.json", rows)
    with (output / "pilot-results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_json(output / "pilot-status.json", {
        "rows": len(rows),
        "arms": dict(Counter(row["arm"] for row in rows)),
        "complete": all(row["complete"] for row in rows),
        "opportunity_policy_execution": rows[0]["opportunity_policy_execution"] if rows else None,
    })
    return rows
