"""Immutable cohort planning and paired analysis for feedback-selection experiments."""

from __future__ import annotations

import json
import math
import random
import shutil
from statistics import NormalDist
from collections import defaultdict
from pathlib import Path

from .data import load_tasks
from .feedback_policy import ARMS, DEFAULT_ADAPTIVE_WEIGHTS
from .io import digest, file_hash, read_jsonl, write_json, write_jsonl

PLAN_FILES = ("tasks.jsonl", "blocks.jsonl", "branches.jsonl", "protocol.json",
              "dataset_manifest.json", "prepared_splits.json", "image_map.json",
              "source_image_map.json")


def create_plan(tasks_dir, output, *, source="swe_bench_lite", task_limit=None, seed=42,
                confirmation_fraction=0.2, minimum_confirmation_incorrect=0,
                allow_local_fixtures=False, image_map_path=None, split=None,
                power=0.80, alpha=0.05, minimum_effect=0.15,
                discordance=0.25, cluster_icc=0.05):
    """Freeze a repository-disjoint task cohort and the five paired policy branches."""
    if not 0 < confirmation_fraction < 1:
        raise ValueError("confirmation_fraction must be strictly between 0 and 1")
    if minimum_confirmation_incorrect < 0:
        raise ValueError("minimum_confirmation_incorrect cannot be negative")
    if not 0 < power < 1 or not 0 < alpha < 1:
        raise ValueError("power and alpha must be strictly between zero and one")
    if not 0 < minimum_effect <= 1 or not 0 < discordance <= 1:
        raise ValueError("minimum_effect and discordance must be in (0, 1]")
    if not 0 <= cluster_icc < 1:
        raise ValueError("cluster_icc must be in [0, 1)")
    if task_limit is not None and task_limit < 1:
        raise ValueError("task_limit must be positive")
    if not allow_local_fixtures and not image_map_path:
        raise ValueError(
            "Benchmark-backed plans require an official `veritas swe image-map` file; "
            "local fixtures require the explicit --allow-local-fixtures flag."
        )
    if not allow_local_fixtures and source not in {"swe_bench_lite", "swe_rebench"}:
        raise ValueError(
            f"Benchmark-backed feedback studies do not support source {source!r}; "
            "use swe_bench_lite or swe_rebench."
        )
    root = Path(output)
    if root.exists() and any(root.iterdir()):
        raise ValueError("Feedback study output must be empty; plans are immutable")
    prepared_manifest = Path(tasks_dir) / "manifest.json"
    if not prepared_manifest.is_file():
        raise ValueError(f"Prepared dataset manifest not found: {prepared_manifest}")
    all_tasks = [task for task, _ in load_tasks(tasks_dir, split=split, source=source)]
    if not all_tasks:
        raise ValueError(f"No tasks found for source={source!r}")
    if any(task.kind != "swe" or not task.repo or not task.base_commit for task in all_tasks):
        raise ValueError("Feedback study requires SWE tasks with repository and pinned base commit")
    supplied_image_map = json.loads(Path(image_map_path).read_text()) if image_map_path else {}
    for task in all_tasks:
        instance_id = task.private.get("instance_id", task.task_id.removeprefix("swe:"))
        mapped_image = supplied_image_map.get(instance_id)
        existing_image = task.private.get("image_name") or task.private.get("docker_image")
        if image_map_path and not mapped_image:
            raise ValueError(f"Pinned image map has no entry for selected task {task.task_id}")
        if mapped_image and existing_image and mapped_image != existing_image:
            raise ValueError(f"Pinned image map disagrees with task metadata for {task.task_id}")
        image_name = mapped_image or existing_image
        if image_name and not (task.private.get("image_name") or task.private.get("docker_image")):
            task.private["image_name"] = image_name
    if not allow_local_fixtures:
        malformed = [task.task_id for task in all_tasks
                     if (task.private.get("image_name") or task.private.get("docker_image"))
                     and not all(key in task.private for key in ("FAIL_TO_PASS", "PASS_TO_PASS", "test_patch"))]
        if malformed:
            raise ValueError(
                f"{len(malformed)} image-backed tasks lack official grading metadata "
                f"(examples: {', '.join(malformed[:5])}). Refusing to create this cohort."
            )
    missing_images = [task.task_id for task in all_tasks
                      if not (task.private.get("image_name") or task.private.get("docker_image"))]
    if missing_images and not allow_local_fixtures:
        all_tasks = [task for task in all_tasks
                     if task.private.get("image_name") or task.private.get("docker_image")]
        if not all_tasks:
            sample = ", ".join(missing_images[:5])
            raise ValueError(
                f"No image-backed tasks are available; {len(missing_images)} tasks lack a "
                f"pinned Docker image (examples: {sample}). Prepare canonical image-backed "
                "task metadata, or explicitly pass --allow-local-fixtures for an engineering pilot."
            )
    if task_limit is not None and task_limit > len(all_tasks):
        raise ValueError(
            f"Requested {task_limit} tasks, but only {len(all_tasks)} eligible tasks "
            "are available after image/grader provenance checks."
        )

    # Limit is selected deterministically across repositories, not by source-file order.
    all_tasks.sort(key=lambda task: digest([seed, task.repo, task.task_id]))
    if task_limit is not None:
        all_tasks = all_tasks[:task_limit]
    repos = sorted({task.repo for task in all_tasks})
    if len(repos) < 2:
        raise ValueError("At least two repositories are needed for repository-disjoint development/confirmation")
    confirmation_count = max(1, round(len(repos) * confirmation_fraction))
    confirmation = set(sorted(repos, key=lambda repo: digest([seed, "confirmation", repo]))[:confirmation_count])
    selected = sorted(all_tasks, key=lambda task: task.task_id)
    confirmation_task_count = sum(task.repo in confirmation for task in selected)
    average_tasks_per_confirmation_repo = confirmation_task_count / len(confirmation)
    power_z_alpha = NormalDist().inv_cdf(1 - alpha)
    power_z_beta = NormalDist().inv_cdf(power)
    independent_required = math.ceil(
        ((power_z_alpha + power_z_beta) ** 2 * max(1e-9, discordance - minimum_effect ** 2))
        / (minimum_effect ** 2)
    )
    cluster_design_effect = 1 + max(0.0, average_tasks_per_confirmation_repo - 1) * cluster_icc
    required_incorrect_parent_blocks = math.ceil(independent_required * cluster_design_effect)
    if required_incorrect_parent_blocks > confirmation_task_count and not allow_local_fixtures:
        raise ValueError(
            f"The confirmation cohort has {confirmation_task_count} tasks, below the approximate "
            f"power target of {required_incorrect_parent_blocks} initially incorrect parents. "
            "Increase the eligible cohort or revise assumptions using development-only evidence."
        )
    if (not allow_local_fixtures
            and minimum_confirmation_incorrect < required_incorrect_parent_blocks):
        raise ValueError(
            "The predeclared confirmation incorrect-parent gate is below the approximate "
            f"power target ({minimum_confirmation_incorrect} < {required_incorrect_parent_blocks}). "
            "Re-plan with a larger --min-confirmation-incorrect or revise the assumptions "
            "using development-only evidence before freezing the cohort."
        )
    if minimum_confirmation_incorrect > confirmation_task_count:
        raise ValueError(
            f"Minimum incorrect-parent gate ({minimum_confirmation_incorrect}) exceeds the "
            f"{confirmation_task_count} planned confirmation tasks"
        )
    selected_images = {
        task.private.get("instance_id", task.task_id.removeprefix("swe:")):
            (task.private.get("image_name") or task.private.get("docker_image"))
        for task in selected if task.private.get("image_name") or task.private.get("docker_image")
    }

    blocks, branches = [], []
    for task in selected:
        partition = "confirmation" if task.repo in confirmation else "development"
        block_id = digest([seed, source, task.task_id, "actor-default", 0])[:24]
        blocks.append({"block_id": block_id, "task_id": task.task_id,
            "repository": task.repo, "partition": partition,
            "draft_seed": 0, "common_parent_required": True})
        for arm in ARMS:
            branches.append({"branch_id": digest([block_id, arm])[:24],
                "block_id": block_id, "task_id": task.task_id, "repository": task.repo,
                "partition": partition, "arm": arm, "status": "planned"})

    root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(prepared_manifest, root / "dataset_manifest.json")
    shutil.copyfile(Path(tasks_dir) / "splits.json", root / "prepared_splits.json")
    write_json(root / "image_map.json", selected_images)
    if image_map_path:
        shutil.copyfile(image_map_path, root / "source_image_map.json")
    else:
        write_json(root / "source_image_map.json", {})
    write_jsonl(root / "tasks.jsonl", (task.model_dump(mode="json") for task in selected))
    write_jsonl(root / "blocks.jsonl", blocks)
    write_jsonl(root / "branches.jsonl", branches)
    protocol = {
        "schema_version": 1, "study": "veritas-feedback-selection",
        "dataset_source": source,
        "dataset_manifest_sha256": file_hash(prepared_manifest),
        "prepared_tasks_sha256": file_hash(Path(tasks_dir) / "tasks.jsonl"),
        "prepared_splits_sha256": file_hash(Path(tasks_dir) / "splits.json"),
        "embedded_prepared_splits_sha256": file_hash(root / "prepared_splits.json"),
        "image_map_sha256": file_hash(root / "image_map.json"),
        "image_map_source_sha256": file_hash(Path(image_map_path)) if image_map_path else None,
        "embedded_source_image_map_sha256": file_hash(root / "source_image_map.json"),
        "source_split_filter": split,
        "seed": seed, "task_count": len(selected), "repository_count": len(repos),
        "development_task_count": sum(task.repo not in confirmation for task in selected),
        "confirmation_task_count": confirmation_task_count,
        "development_repositories": sorted(set(repos) - confirmation),
        "confirmation_repositories": sorted(confirmation),
        "arms": list(ARMS), "primary_comparison": ["adaptive", "fixed_actionable"],
        "minimum_confirmation_incorrect": minimum_confirmation_incorrect,
        "minimum_confirmation_repositories_for_cluster_inference": 10,
        "power_analysis": {
            "method": "normal_approximation_for_paired_binary_difference_with_cluster_design_effect",
            "power": power, "alpha_one_sided": alpha,
            "minimum_meaningful_risk_difference": minimum_effect,
            "assumed_paired_discordance": discordance,
            "assumed_repository_icc": cluster_icc,
            "average_tasks_per_confirmation_repository": average_tasks_per_confirmation_repo,
            "cluster_design_effect": cluster_design_effect,
            "required_incorrect_parent_blocks_approx": required_incorrect_parent_blocks,
            "planned_confirmation_tasks": confirmation_task_count,
            "confirmation_repositories": len(confirmation),
            "adequately_sized_by_task_count": confirmation_task_count >= required_incorrect_parent_blocks,
            "caveat": "Approximation only; few independent repositories can invalidate task-count power assumptions.",
        },
        "environment_mode": "local_fixtures" if allow_local_fixtures else "pinned_images",
        "unimageable_tasks_excluded": len(missing_images) if not allow_local_fixtures else 0,
        "design": "paired branches from a single independently graded common parent patch",
        "note": "Planning only. Branch execution must freeze one parent patch per block before treatment branches are run.",
    }
    write_json(root / "protocol.json", protocol)
    plan = {"files": {name: file_hash(root / name) for name in PLAN_FILES}}
    plan["plan_hash"] = digest(plan)
    write_json(root / "plan.json", plan)
    return {"plan_hash": plan["plan_hash"], "tasks": len(selected),
            "repositories": len(repos), "branches": len(branches),
            "development_tasks": sum(task.repo not in confirmation for task in selected),
            "confirmation_tasks": confirmation_task_count,
            "development_repositories": len(repos) - len(confirmation),
            "confirmation_repositories": len(confirmation), "output": str(root)}


def verify_plan(directory):
    root = Path(directory)
    plan = json.loads((root / "plan.json").read_text())
    if digest({"files": plan.get("files")}) != plan.get("plan_hash"):
        raise ValueError("Feedback plan hash mismatch")
    for name, expected in plan["files"].items():
        if file_hash(root / name) != expected:
            raise ValueError(f"Feedback plan artifact changed: {name}")
    tasks = list(read_jsonl(root / "tasks.jsonl"))
    blocks = list(read_jsonl(root / "blocks.jsonl"))
    branches = list(read_jsonl(root / "branches.jsonl"))
    if len(branches) != len(blocks) * len(ARMS):
        raise ValueError("Every block must have exactly one branch per frozen arm")
    if len({task["task_id"] for task in tasks}) != len(tasks):
        raise ValueError("Duplicate task IDs in plan")
    for block in blocks:
        arms = [branch["arm"] for branch in branches if branch["block_id"] == block["block_id"]]
        if sorted(arms) != sorted(ARMS):
            raise ValueError(f"Incomplete or duplicate arms for block {block['block_id']}")
    protocol = json.loads((root / "protocol.json").read_text())
    if protocol.get("environment_mode") not in {"pinned_images", "local_fixtures"}:
        raise ValueError("Unknown study environment mode")
    if int(protocol.get("minimum_confirmation_incorrect", 0)) < 0:
        raise ValueError("Invalid minimum confirmation incorrect-parent threshold")
    manifest = json.loads((root / "dataset_manifest.json").read_text())
    source_splits = json.loads((root / "prepared_splits.json").read_text())
    source_receipt = (manifest.get("sources") or {}).get(protocol.get("dataset_source"))
    if not source_receipt or not isinstance(source_receipt.get("spec"), dict):
        raise ValueError("Pinned dataset manifest has no receipt for the selected source")
    source_spec = source_receipt["spec"]
    canonical_task_ids = set((manifest.get("aliases") or {}).values())
    if file_hash(root / "dataset_manifest.json") != protocol.get("dataset_manifest_sha256"):
        raise ValueError("Embedded dataset manifest does not match the pinned source hash")
    if file_hash(root / "prepared_splits.json") != protocol.get("prepared_splits_sha256"):
        raise ValueError("Embedded prepared split map does not match the pinned source hash")
    if file_hash(root / "prepared_splits.json") != protocol.get("embedded_prepared_splits_sha256"):
        raise ValueError("Embedded prepared split map hash is inconsistent")
    if manifest.get("tasks_sha256") != protocol.get("prepared_tasks_sha256"):
        raise ValueError("Prepared task file hash does not match the embedded dataset manifest")
    if manifest.get("splits_sha256") != protocol.get("prepared_splits_sha256"):
        raise ValueError("Prepared split file hash does not match the embedded dataset manifest")
    expected_split = protocol.get("source_split_filter")
    for row in tasks:
        task_id = row["task_id"]
        if task_id not in source_splits:
            raise ValueError(f"Selected task {task_id} is absent from the pinned prepared split map")
        if expected_split and source_splits[task_id].get("split") != expected_split:
            raise ValueError(f"Selected task {task_id} does not belong to requested split {expected_split}")
        if row.get("source") != protocol.get("dataset_source"):
            raise ValueError(f"Selected task {task_id} has an unexpected dataset source")
        if task_id not in canonical_task_ids:
            raise ValueError(f"Selected task {task_id} is absent from pinned source task aliases")
        if row.get("source_revision") != source_spec.get("revision"):
            raise ValueError(f"Selected task {task_id} does not match the pinned source revision")
        if row.get("source_split") != source_spec.get("split"):
            raise ValueError(f"Selected task {task_id} does not match the pinned source release split")
    task_by_id = {row["task_id"]: row for row in tasks}
    if len(blocks) != len(tasks) or {b.get("task_id") for b in blocks} != set(task_by_id):
        raise ValueError("Frozen blocks do not map one-to-one to the selected task IDs")
    if file_hash(root / "image_map.json") != protocol.get("image_map_sha256"):
        raise ValueError("Embedded image map does not match the pinned image hash")
    if file_hash(root / "source_image_map.json") != protocol.get("embedded_source_image_map_sha256"):
        raise ValueError("Embedded source image map hash is inconsistent")
    source_image_map = json.loads((root / "source_image_map.json").read_text())
    if protocol.get("image_map_source_sha256") is None:
        if source_image_map:
            raise ValueError("Plan contains a source image map without its source hash")
    elif file_hash(root / "source_image_map.json") != protocol.get("image_map_source_sha256"):
        raise ValueError("Embedded source image map does not match its original file hash")
    if protocol.get("environment_mode") == "pinned_images":
        image_map = json.loads((root / "image_map.json").read_text())
        missing_images = [row["task_id"] for row in tasks
                          if not ((row.get("private") or {}).get("image_name")
                                  or (row.get("private") or {}).get("docker_image"))]
        if missing_images:
            raise ValueError(f"Pinned-image plan contains {len(missing_images)} task(s) without images")
        for row in tasks:
            private = row.get("private") or {}
            if not all(key in private for key in ("FAIL_TO_PASS", "PASS_TO_PASS", "test_patch")):
                raise ValueError(f"Pinned-image plan lacks official grader metadata for {row['task_id']}")
            instance_id = private.get("instance_id", row["task_id"].removeprefix("swe:"))
            expected_image = private.get("image_name") or private.get("docker_image")
            if image_map.get(instance_id) != expected_image:
                raise ValueError(f"Pinned image map disagrees with task metadata for {row['task_id']}")
            if source_image_map.get(instance_id) != expected_image:
                raise ValueError(f"Selected image is not present in the official source image map for {row['task_id']}")
    if set(protocol["development_repositories"]) & set(protocol["confirmation_repositories"]):
        raise ValueError("Development and confirmation repositories overlap")
    dev_repos = set(protocol["development_repositories"])
    conf_repos = set(protocol["confirmation_repositories"])
    dev_task_count = sum(block.get("partition") == "development" for block in blocks)
    conf_task_count = sum(block.get("partition") == "confirmation" for block in blocks)
    if len(tasks) != protocol.get("task_count") or len({t.get("repo") for t in tasks}) != protocol.get("repository_count"):
        raise ValueError("Frozen cohort counts do not match the pinned protocol")
    if dev_task_count != protocol.get("development_task_count") or conf_task_count != protocol.get("confirmation_task_count"):
        raise ValueError("Frozen partition task counts do not match the pinned protocol")
    for block in blocks:
        task = task_by_id.get(block.get("task_id"))
        if task is None or task.get("repo") != block.get("repository"):
            raise ValueError(f"Block task/repository provenance mismatch: {block.get('block_id')}")
        expected_partition = "confirmation" if block["repository"] in conf_repos else "development"
        if block.get("partition") != expected_partition or block["repository"] not in dev_repos | conf_repos:
            raise ValueError(f"Block partition does not match frozen repository split: {block['block_id']}")
    return {"plan_hash": plan["plan_hash"], "integrity": "valid", "tasks": len(tasks),
            "blocks": len(blocks), "branches": len(branches),
            "development_tasks": dev_task_count, "confirmation_tasks": conf_task_count,
            "development_repositories": len(dev_repos), "confirmation_repositories": len(conf_repos)}


def freeze_baseline(directory, results_path=None, *, minimum_incorrect=20,
                    selector_weights=None, selector_weights_sha256=None):
    """Freeze the strongest fixed feedback arm using development data only."""
    root = Path(directory)
    if minimum_incorrect < 1:
        raise ValueError("minimum_incorrect must be at least 1")
    verify_plan(root)
    if (root / "frozen_baseline.json").exists():
        raise ValueError("A fixed baseline is already frozen; create a new study to change it")
    results_path = Path(results_path) if results_path else root / "results.jsonl"
    results = list(read_jsonl(results_path))
    development_rows = [row for row in results if row.get("partition") == "development"]
    if not development_rows:
        raise ValueError("No development results are available to freeze a baseline")
    blocks = {b["block_id"]: b for b in read_jsonl(root / "blocks.jsonl")
              if b.get("partition") == "development"}
    planned = {(row["block_id"], row["arm"]): row["branch_id"]
               for row in read_jsonl(root / "branches.jsonl")
               if row.get("partition") == "development"}
    by_block = defaultdict(dict)
    for row in development_rows:
        block = blocks.get(row.get("block_id"))
        if block is None:
            raise ValueError("Development results contain a row outside the frozen development partition")
        if row.get("arm") not in ARMS:
            raise ValueError("Development results contain an unknown arm")
        if row.get("branch_id") != planned.get((row["block_id"], row["arm"])):
            raise ValueError("Development result does not match its frozen branch assignment")
        if row["arm"] in by_block[row["block_id"]]:
            raise ValueError("Duplicate development outcome for a block/arm")
        by_block[row["block_id"]][row["arm"]] = row
    incomplete = [bid for bid in blocks
                  if set(by_block.get(bid, {})) != set(ARMS)]
    if incomplete:
        raise ValueError(
            f"Cannot freeze the fixed baseline: {len(incomplete)} development blocks do not "
            "have outcomes for every planned arm. Complete the full development partition first."
        )
    development_snapshot = root / "development_results_frozen.jsonl"
    write_jsonl(development_snapshot, development_rows)
    incorrect = [bid for bid, arms in by_block.items()
                 if arms.get("adaptive", {}).get("parent_resolved") is False]
    if len(incorrect) < minimum_incorrect:
        raise ValueError(
            f"Cannot freeze a development baseline: only {len(incorrect)} initially incorrect "
            f"development parents; require at least {minimum_incorrect}. Plan/run a larger "
            "development cohort before confirmation."
        )
    fixed_arms = [arm for arm in ARMS if arm != "adaptive"]
    scores = {}
    for arm in fixed_arms:
        observed = [by_block[bid][arm] for bid in incorrect if arm in by_block[bid]
                    and by_block[bid][arm].get("resolved") in (True, False)]
        if len(observed) != len(incorrect):
            raise ValueError(f"Development results are incomplete for fixed arm {arm}")
        successes = sum(row["resolved"] is True for row in observed)
        costs = [float(row["total_credits"]) for row in observed
                 if row.get("total_credits") is not None]
        scores[arm] = {"successes": successes, "total": len(observed),
                       "recovery_rate": successes / len(observed),
                       "mean_credits": sum(costs) / len(costs) if costs else None}
    # Maximize recovery, then minimize cost, then use frozen arm order.
    selected = min(fixed_arms, key=lambda arm: (
        -scores[arm]["recovery_rate"],
        scores[arm]["mean_credits"] if scores[arm]["mean_credits"] is not None else float("inf"),
        fixed_arms.index(arm),
    ))
    weights = dict(DEFAULT_ADAPTIVE_WEIGHTS)
    weight_status = "prespecified_heuristic_defaults"
    if selector_weights is not None:
        if set(selector_weights) != set(DEFAULT_ADAPTIVE_WEIGHTS):
            raise ValueError(f"Selector weights must have exactly these keys: {sorted(DEFAULT_ADAPTIVE_WEIGHTS)}")
        try:
            weights = {key: float(selector_weights[key]) for key in DEFAULT_ADAPTIVE_WEIGHTS}
        except (TypeError, ValueError) as exc:
            raise ValueError("Selector weights must be finite numbers") from exc
        if any(not math.isfinite(value) for value in weights.values()):
            raise ValueError("Selector weights must be finite numbers")
        weight_status = "user_supplied_and_frozen_before_confirmation; provenance_not_independently_validated"
    artifact = {
        "schema_version": 1,
        "plan_hash": json.loads((root / "plan.json").read_text())["plan_hash"],
        "selection_data_partition": "development",
        "selection_rule": "highest recovery among initially incorrect parents; tie-break lower mean credits; then frozen arm order",
        "minimum_incorrect_required": minimum_incorrect,
        "incorrect_parent_blocks": len(incorrect),
        "development_results_sha256": file_hash(development_snapshot),
        "fixed_arm_scores": scores,
        "selected_fixed_arm": selected,
        "selector_weights": weights,
        "selector_weights_status": weight_status,
        "selector_weights_source_sha256": selector_weights_sha256,
    }
    artifact["content_hash"] = digest(artifact)
    write_json(root / "frozen_baseline.json", artifact)
    return artifact


def verify_frozen_baseline(directory):
    root = Path(directory)
    path = root / "frozen_baseline.json"
    if not path.is_file():
        raise ValueError("Confirmation requires frozen_baseline.json from development-only selection")
    artifact = json.loads(path.read_text(encoding="utf-8"))
    saved_hash = artifact.pop("content_hash", None)
    if saved_hash != digest(artifact):
        raise ValueError("Frozen baseline integrity check failed")
    plan_hash = json.loads((root / "plan.json").read_text())["plan_hash"]
    if artifact.get("plan_hash") != plan_hash or artifact.get("selection_data_partition") != "development":
        raise ValueError("Frozen baseline does not match this plan or development partition")
    snapshot = root / "development_results_frozen.jsonl"
    if not snapshot.is_file() or file_hash(snapshot) != artifact.get("development_results_sha256"):
        raise ValueError("Frozen development results are missing or changed")
    if artifact.get("selected_fixed_arm") not in ARMS or artifact["selected_fixed_arm"] == "adaptive":
        raise ValueError("Frozen baseline must select a fixed feedback arm")
    artifact["content_hash"] = saved_hash
    return artifact


def analyze_results(directory, results_path=None, *, partition=None):
    """Summarize all five arms and the paired E-vs-C comparison descriptively.

    Pilot outputs include uncertainty intervals and denominators, but deliberately
    do not label small-sample p-values as confirmatory evidence.
    """
    root = Path(directory)
    verify_plan(root)
    results_path = Path(results_path) if results_path else root / "results.jsonl"
    if not results_path.is_file():
        raise ValueError(f"Branch outcome ledger not found: {results_path}")
    results = list(read_jsonl(results_path))
    all_blocks = list(read_jsonl(root / "blocks.jsonl"))
    if partition not in (None, "development", "confirmation"):
        raise ValueError("partition must be development, confirmation, or omitted")
    selected_block_ids = {b["block_id"] for b in all_blocks
                          if partition is None or b.get("partition") == partition}
    results = [row for row in results if row.get("block_id") in selected_block_ids]
    comparison_arm = "fixed_actionable"
    if partition == "confirmation":
        comparison_arm = verify_frozen_baseline(root)["selected_fixed_arm"]
    by_block = defaultdict(dict)
    planned = {(row["block_id"], row["arm"]): row for row in read_jsonl(root / "branches.jsonl")
               if row["block_id"] in selected_block_ids}
    for row in results:
        if row.get("arm") not in ARMS:
            raise ValueError("Unknown feedback arm in results")
        assignment = planned.get((row.get("block_id"), row["arm"]))
        if assignment is None or row.get("branch_id") != assignment["branch_id"]:
            raise ValueError("Result does not match a frozen branch assignment")
        if row["arm"] in by_block[row["block_id"]]:
            raise ValueError("Duplicate block/arm outcome")
        by_block[row["block_id"]][row["arm"]] = row
    paired = []
    per_arm = {}
    by_repository = {}
    # Report all five arms for both partitions. In confirmation, only the
    # adaptive-vs-frozen-development-arm contrast is primary; the remaining
    # arm summaries are secondary and descriptive.
    selected_arms = ARMS
    for arm in selected_arms:
        rows = [row for row in results if row.get("arm") == arm]
        planned_count = sum(1 for block_id, planned_arm in planned if planned_arm == arm)
        graded = [row for row in rows if row.get("resolved") in (True, False)]
        resolved = sum(row.get("resolved") is True for row in graded)
        unresolved = sum(row.get("resolved") is False for row in graded)
        empty = sum(bool(row.get("patch_empty")) for row in rows)
        infra = sum(row.get("grader_status") == "infrastructure_error" for row in rows)
        all_recorded_denominator = len(rows)
        per_arm[arm] = {
            "planned": planned_count,
            "recorded": len(rows),
            "graded_nonempty": len(graded),
            "resolved": resolved,
            "unresolved": unresolved,
            "empty_patch": empty,
            "grader_infrastructure_error": infra,
            "unrecorded": max(0, planned_count - len(rows)),
            "resolution_rate_graded": _rate_with_wilson(resolved, len(graded)),
            "resolved_share_recorded": _rate_with_wilson(resolved, all_recorded_denominator),
            "mean_estimated_credits": _mean([
                row["total_credits"] for row in rows if row.get("total_credits") is not None
            ]),
            "mean_wall_seconds": _mean([
                row["wall_seconds"] for row in rows if row.get("wall_seconds") is not None
            ]),
            "mean_steps": _mean([row["steps"] for row in rows if row.get("steps") is not None]),
        }
        repo_stats = {}
        for repo in sorted({row.get("repository", "unknown") for row in rows}):
            repo_rows = [row for row in rows if row.get("repository", "unknown") == repo]
            repo_graded = [row for row in repo_rows if row.get("resolved") in (True, False)]
            repo_resolved = sum(row.get("resolved") is True for row in repo_graded)
            repo_stats[repo] = {
                "recorded": len(repo_rows), "graded_nonempty": len(repo_graded),
                "resolved": repo_resolved,
                "resolution_rate_graded": _rate_with_wilson(repo_resolved, len(repo_graded)),
            }
        test_regression_known = [row for row in rows
                                 if row.get("preexisting_test_regression") in (True, False)]
        test_regressions = sum(row.get("preexisting_test_regression") is True
                               for row in test_regression_known)
        by_repository[arm] = repo_stats
        per_arm[arm]["preexisting_test_regression"] = {
            "regressions": test_regressions,
            "known": len(test_regression_known),
            "unknown_or_unavailable": len(rows) - len(test_regression_known),
            "rate_known": _rate_with_wilson(test_regressions, len(test_regression_known)),
        }

    parent_labels = {}
    for block in read_jsonl(root / "blocks.jsonl"):
        grade_path = root / "blocks" / block["block_id"] / "parent_grade.json"
        if grade_path.is_file():
            try:
                parent_labels[block["block_id"]] = json.loads(
                    grade_path.read_text(encoding="utf-8")
                ).get("parent_resolved")
            except (OSError, ValueError):
                parent_labels[block["block_id"]] = None
    for block in read_jsonl(root / "blocks.jsonl"):
        arms = by_block.get(block["block_id"], {})
        adaptive, fixed = arms.get("adaptive", {}), arms.get(comparison_arm, {})
        parent_correct = parent_labels.get(block["block_id"])
        if parent_correct is None:
            parent_correct = adaptive.get("parent_resolved", fixed.get("parent_resolved"))
        # Keep every block with known pre-treatment parent status. Missing or
        # ungradable assigned branch outcomes remain in the ITT denominator and
        # are conservatively counted as not resolved; complete-case results are
        # reported separately below.
        if parent_correct not in (True, False):
            continue
        paired.append({"block_id": block["block_id"], "repository": block["repository"],
            "partition": block["partition"], "parent_resolved": parent_correct,
            "adaptive_resolved": adaptive.get("resolved") is True,
            "comparison_resolved": fixed.get("resolved") is True,
            "adaptive_outcome_known": adaptive.get("resolved") in (True, False),
            "comparison_outcome_known": fixed.get("resolved") in (True, False),
            "adaptive_credits": adaptive.get("total_credits"),
            "comparison_credits": fixed.get("total_credits")})
    complete_pairs = [row for row in paired if row["adaptive_outcome_known"]
                      and row["comparison_outcome_known"]]
    incorrect = [row for row in paired if row["parent_resolved"] is False]
    incorrect_complete = [row for row in complete_pairs if row["parent_resolved"] is False]
    # Regression is also intention-to-treat: a missing/unknown final grade for
    # a parent-correct block cannot be silently dropped from this guardrail.
    correct = [row for row in paired if row["parent_resolved"] is True]
    adaptive_wins = sum(r["adaptive_resolved"] and not r["comparison_resolved"] for r in incorrect)
    fixed_wins = sum(r["comparison_resolved"] and not r["adaptive_resolved"] for r in incorrect)
    paired_ties = len(incorrect) - adaptive_wins - fixed_wins
    adaptive_costs = [row["adaptive_credits"] for row in paired if row["adaptive_credits"] is not None]
    fixed_costs = [row["comparison_credits"] for row in paired
                   if row["comparison_credits"] is not None]
    cluster_interval = _cluster_bootstrap_difference(
        incorrect, seed=int(json.loads((root / "protocol.json").read_text()).get("seed", 0))
    )
    plan_protocol = json.loads((root / "protocol.json").read_text())
    confirmation_screen = {"graded": 0, "incorrect": 0, "unknown_or_missing": 0}
    if partition == "confirmation":
        for block in all_blocks:
            if block.get("partition") != "confirmation":
                continue
            grade_path = root / "blocks" / block["block_id"] / "parent_grade.json"
            if not grade_path.is_file():
                confirmation_screen["unknown_or_missing"] += 1
                continue
            parent_grade = json.loads(grade_path.read_text(encoding="utf-8"))
            parent_value = parent_grade.get("parent_resolved")
            if parent_value not in (True, False):
                confirmation_screen["unknown_or_missing"] += 1
            else:
                confirmation_screen["graded"] += 1
                confirmation_screen["incorrect"] += parent_value is False
    confirmation_primary_complete = (partition != "confirmation" or all(
        block_id in by_block
        and by_block[block_id].get("adaptive", {}).get("resolved") in (True, False)
        and by_block[block_id].get(comparison_arm, {}).get("resolved") in (True, False)
        for block_id in selected_block_ids
    ))
    confirmation_all_arms_complete = (partition != "confirmation" or all(
        by_block.get(block_id, {}).get(arm, {}).get("resolved") in (True, False)
        for block_id in selected_block_ids for arm in ARMS
    ))
    confirmation_outcomes_complete = confirmation_primary_complete and confirmation_all_arms_complete
    confirmation_gate_satisfied = (
        partition != "confirmation"
        or (confirmation_screen["unknown_or_missing"] == 0
            and confirmation_screen["incorrect"] >= int(plan_protocol.get("minimum_confirmation_incorrect", 0)))
    )
    power_plan = plan_protocol.get("power_analysis")
    power_required = (power_plan or {}).get("required_incorrect_parent_blocks_approx")
    confirmation_power_sufficient = (
        partition != "confirmation" or power_required is None
        or confirmation_screen["incorrect"] >= int(power_required)
    )
    confirmation_repository_count = len({
        block["repository"] for block in all_blocks if block.get("partition") == "confirmation"
    })
    cluster_count_target = int(plan_protocol.get(
        "minimum_confirmation_repositories_for_cluster_inference", 10
    ))
    # A task-count approximation cannot substitute for independent clusters.
    # Below the predeclared cluster target, report task-paired results as
    # descriptive and state the limited cross-repository generalization.
    enough_confirmation_clusters = confirmation_repository_count >= cluster_count_target
    return {"paired_blocks": len(paired), "incorrect_parent_blocks": len(incorrect),
        "parent_correct_paired_blocks": len(correct),
        "parent_unknown_or_unpaired_blocks": max(0, len(selected_block_ids) - len(paired)),
        "arms": per_arm, "by_repository": by_repository,
        "primary_paired": {
            "comparison": f"adaptive vs {comparison_arm} among initially incorrect parents",
            "paired_n": len(incorrect),
            "adaptive_only_resolved": adaptive_wins,
            "fixed_only_resolved": fixed_wins,
            "both_or_neither_tied": paired_ties,
            "adaptive_recovery_rate": _rate_with_wilson(
                sum(r["adaptive_resolved"] for r in incorrect), len(incorrect)
            ),
            "comparison_recovery_rate": _rate_with_wilson(
                sum(r["comparison_resolved"] for r in incorrect), len(incorrect)
            ),
            "risk_difference_adaptive_minus_comparison": _mean([
                int(r["adaptive_resolved"]) - int(r["comparison_resolved"]) for r in incorrect
            ]),
            "repository_cluster_bootstrap_95ci": cluster_interval,
            "intention_to_treat": True,
            "assigned_incorrect_parent_blocks": len(incorrect),
            "unknown_adaptive_outcomes_counted_unresolved": sum(not r["adaptive_outcome_known"] for r in incorrect),
            "unknown_comparison_outcomes_counted_unresolved": sum(not r["comparison_outcome_known"] for r in incorrect),
            "complete_case_paired_n": len(incorrect_complete),
        },
        "complete_case_primary": {
            "paired_n": len(incorrect_complete),
            "adaptive_recovery_rate": _rate_with_wilson(
                sum(r["adaptive_resolved"] for r in incorrect_complete), len(incorrect_complete)
            ),
            "comparison_recovery_rate": _rate_with_wilson(
                sum(r["comparison_resolved"] for r in incorrect_complete), len(incorrect_complete)
            ),
        },
        "all_block_adaptive_resolution": _mean([r["adaptive_resolved"] for r in paired]),
        "all_block_comparison_resolution": _mean([r["comparison_resolved"] for r in paired]),
        "recovery_adaptive": _mean([r["adaptive_resolved"] for r in incorrect]),
        "recovery_comparison": _mean([r["comparison_resolved"] for r in incorrect]),
        "regression_adaptive": _mean([not r["adaptive_resolved"] for r in correct]),
        "regression_comparison": _mean([not r["comparison_resolved"] for r in correct]),
        "regression_adaptive_unknown_outcomes_counted_as_regressions": sum(
            not r["adaptive_outcome_known"] for r in correct
        ),
        "regression_comparison_unknown_outcomes_counted_as_regressions": sum(
            not r["comparison_outcome_known"] for r in correct
        ),
        "paired_recovery_difference": _mean([
            int(r["adaptive_resolved"]) - int(r["comparison_resolved"]) for r in incorrect
        ]),
        "mean_adaptive_credits": _mean(adaptive_costs),
        "mean_comparison_credits": _mean(fixed_costs),
        "analysis_status": (
            "confirmation_repository_cluster_bootstrap"
            if partition == "confirmation" and confirmation_outcomes_complete
            and confirmation_gate_satisfied and confirmation_power_sufficient
            and enough_confirmation_clusters
            else "confirmation_low_cluster_count_task_paired_descriptive"
            if partition == "confirmation" and confirmation_outcomes_complete
            and confirmation_gate_satisfied and confirmation_power_sufficient
            else "confirmation_underpowered_descriptive"
            if partition == "confirmation" and confirmation_outcomes_complete
            and confirmation_gate_satisfied
            else "confirmation_gate_failed_descriptive"
            if partition == "confirmation" and confirmation_outcomes_complete
            else "confirmation_incomplete_descriptive" if partition == "confirmation"
            else "development_descriptive_unclustered"
        ),
        "analysis_partition": partition or "all",
        "comparison_arm": comparison_arm,
        "primary_comparison": {
            "adaptive_arm": "adaptive",
            "frozen_comparator_arm": comparison_arm,
            "secondary_arms": [arm for arm in ARMS if arm not in {"adaptive", comparison_arm}],
        },
        "confirmation_gate": {
            "minimum_incorrect_predeclared": plan_protocol.get("minimum_confirmation_incorrect", 0),
            "parent_screening": confirmation_screen if partition == "confirmation" else None,
            "incorrect_parent_blocks_with_paired_outcomes": len(incorrect),
            "complete_primary_pairs_for_all_confirmation_blocks": confirmation_primary_complete,
            "complete_five_arm_outcomes_for_all_confirmation_blocks": confirmation_all_arms_complete,
            "complete_paired_outcomes_for_all_confirmation_blocks": confirmation_outcomes_complete,
            "satisfied": (confirmation_gate_satisfied and confirmation_outcomes_complete
                          and confirmation_power_sufficient and enough_confirmation_clusters),
            "power_sufficient_by_predeclared_task_count_approximation": confirmation_power_sufficient,
            "confirmation_repository_count": confirmation_repository_count if partition == "confirmation" else None,
            "minimum_repositories_for_cluster_inference": cluster_count_target,
            "enough_independent_repositories_for_cluster_inference": enough_confirmation_clusters,
            "predeclared_power_analysis": power_plan,
            "observed_incorrect_parent_blocks": confirmation_screen["incorrect"] if partition == "confirmation" else None,
        },
        "note": "The confirmation estimate uses a repository-cluster bootstrap. Confirmatory claims still require a predeclared power analysis and adequate independent repository clusters."}


def _mean(values):
    return sum(float(v) for v in values) / len(values) if values else None


def _rate_with_wilson(successes, total, confidence=0.95):
    """Return a Wilson score interval, including its explicit denominator."""
    if total <= 0:
        return {"successes": successes, "total": total, "rate": None, "ci95": None}
    z = NormalDist().inv_cdf(0.5 + confidence / 2)
    p = successes / total
    z2 = z * z
    denom = 1 + z2 / total
    center = (p + z2 / (2 * total)) / denom
    radius = z * math.sqrt((p * (1 - p) / total) + z2 / (4 * total * total)) / denom
    return {"successes": successes, "total": total, "rate": p,
            "ci95": [max(0.0, center - radius), min(1.0, center + radius)]}


def _cluster_bootstrap_difference(rows, *, seed, replicates=10000):
    """Percentile interval resampling repositories, retaining paired tasks within each."""
    clusters = defaultdict(list)
    for row in rows:
        clusters[row["repository"]].append(row)
    names = sorted(clusters)
    if len(names) < 2:
        return {"ci95": None, "clusters": len(names), "replicates": 0,
                "warning": "At least two repository clusters are required"}
    rng = random.Random(seed)
    differences = []
    for _ in range(replicates):
        sampled = [rng.choice(names) for _ in names]
        sample = [row for name in sampled for row in clusters[name]]
        differences.append(sum(int(r["adaptive_resolved"]) - int(r["comparison_resolved"])
                               for r in sample) / len(sample))
    differences.sort()
    lo = differences[int(0.025 * (replicates - 1))]
    hi = differences[int(0.975 * (replicates - 1))]
    return {"ci95": [lo, hi], "clusters": len(names), "replicates": replicates,
            "seed": seed, "warning": ("Few repository clusters; interval is unstable" if len(names) < 10 else None)}
