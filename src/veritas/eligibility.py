"""Fail-closed model-size and original-source checks for experiment planning."""
import json
import re
from pathlib import Path

import yaml

from .data import normalize
from .io import digest, file_hash, read_jsonl


def eligible_models(server, models, maximum):
    if maximum is None:
        return models, []
    if server.backend != "ollama":
        raise ValueError("Parameter-capped comparisons require Ollama metadata")
    selected, excluded = [], []
    for model in models:
        count = model.get("parameter_count")
        if type(count) is not int or count <= 0:
            reason = "Exact parameter count unavailable; cannot verify size cap"
        elif count > maximum * 1_000_000_000:
            reason = f"Total parameters exceed {maximum:g}B cap"
        elif not model.get("capabilities") or "completion" not in model["capabilities"]:
            reason = "Completion capability unconfirmed"
        else:
            selected.append(model)
            continue
        excluded.append({**model, "reason": reason})
    if not selected:
        raise ValueError(f"No eligible Ollama models at or below {maximum:g}B: {excluded}")
    return selected, excluded


def verify_original_tasks(tasks, manifest, registry, raw_dir):
    """Match selected task contents to checksummed, pinned original download records.

    Local receipts are integrity evidence, not independent proof of upstream authorship.
    No generated, substituted or augmented task contents are accepted.
    """
    specs = yaml.safe_load(Path(registry).read_text())["sources"]
    grouped = {}
    for task, _ in tasks:
        grouped.setdefault(task.source, []).append(task)
    evidence = {}
    for source, selected in grouped.items():
        receipt = manifest["sources"].get(source, {})
        spec = specs.get(source)
        if (not spec or receipt.get("original_data") is not True
                or receipt.get("spec") != spec
                or not re.fullmatch(r"[0-9a-f]{40}", spec.get("revision", ""))):
            raise ValueError(f"Original pinned provenance missing or mismatched: {source}")
        path = Path(raw_dir) / f"{source}.jsonl"
        downloaded = json.loads(path.with_suffix(".manifest.json").read_text())
        if downloaded != receipt or file_hash(path) != receipt.get("sha256"):
            raise ValueError(f"Original raw dataset integrity failure: {source}")

        def fingerprint(task):
            # Preparation may merge duplicate IDs and declare a research-pool holdout split.
            return digest(task.model_dump(mode="json", exclude={
                "task_id", "group_id", "official_holdout"
            }))

        remaining = {fingerprint(task) for task in selected}
        for row in read_jsonl(path):
            remaining.discard(fingerprint(normalize(row, source, spec)))
        if remaining:
            raise ValueError(f"Selected tasks differ from original source records: {source}")
        evidence[source] = {
            "repo": spec["repo"], "revision": spec["revision"],
            "raw_sha256": receipt["sha256"], "selected_tasks_verified": len(selected),
        }
    return evidence
