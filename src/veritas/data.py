import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from .io import digest, file_hash, read_jsonl, write_json, write_jsonl
from .schema import Task

SPLITS = [("dev", 0.10), ("calib", 0.25), ("val", 0.20), ("test", 0.35), ("backbone", 0.10)]


def download(manifest, names, output, limit=None):
    """Fetch original releases; revisions must be immutable HF commit hashes."""
    from datasets import load_dataset

    specs = yaml.safe_load(Path(manifest).read_text())["sources"]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    results = {}
    for name in names:
        spec = specs[name]
        rev = spec["revision"]
        if len(rev) != 40 or any(c not in "0123456789abcdef" for c in rev):
            raise ValueError(f"{name}: revision must be a 40-character commit SHA")
        target = output / f"{name}.jsonl"
        receipt = output / f"{name}.manifest.json"
        if target.exists() and receipt.exists():
            old = json.loads(receipt.read_text())
            if old["spec"] == spec and old["limit"] == limit and old["sha256"] == file_hash(target):
                results[name] = old
                continue
            raise ValueError(f"Existing dataset differs: {target}; choose a new output directory")
        ds = load_dataset(
            spec["repo"],
            name=spec.get("config"),
            revision=rev,
            split=spec["split"],
            cache_dir=str(output / ".hf-cache"),
        )
        if len(ds) != spec["expected_rows"]:
            raise ValueError(f"{name}: expected {spec['expected_rows']} rows, got {len(ds)}")
        if limit is not None:
            if limit < 1:
                raise ValueError("limit must be positive")
            ds = ds.select(range(min(limit, len(ds))))
        write_jsonl(target, iter(ds))
        result = {
            "spec": spec,
            "rows": len(ds),
            "limit": limit,
            "sha256": file_hash(target),
            "original_data": True,
        }
        write_json(receipt, result)
        results[name] = result
        print(f"Downloaded {name}: {len(ds):,} original rows", flush=True)
    return results


def normalize(row, name, spec):
    kind = spec["adapter"]
    if kind == "swe":
        identity = "swe:" + row["instance_id"]
        prompt = row["problem_statement"]
        repo, base = row["repo"], row["base_commit"]
    elif kind in {"gsm8k", "math"}:
        prompt = row["question"] if kind == "gsm8k" else row["problem"]
        identity = kind + ":" + digest(" ".join(prompt.split()))[:24]
        repo, base = None, None
    else:
        raise ValueError(f"Unsupported dataset adapter {kind}")
    return Task(
        task_id=identity,
        group_id=identity,
        source=name,
        source_revision=spec["revision"],
        source_split=spec["split"],
        kind=kind,
        prompt=prompt,
        official_holdout=spec["official_holdout"],
        repo=repo,
        base_commit=base,
        private=row,
    )


def prepare(manifest, raw_dir, output, seed=42, research_pool=None):
    """Deduplicate across releases, then stratify by domain/repository at task level."""
    specs = yaml.safe_load(Path(manifest).read_text())["sources"]
    research_pool = set(research_pool or [])
    if not research_pool <= {"swe_test", "swe_rebench"}:
        raise ValueError(
            "Only swe_test and swe_rebench may be repartitioned as a declared research pool; Verified/GSM8K/MATH holdouts remain frozen"
        )
    tasks, fingerprint_ids, aliases = {}, {}, {}
    receipts = {}
    for name, spec in specs.items():
        path = Path(raw_dir) / f"{name}.jsonl"
        if not path.exists():
            continue
        receipt = json.loads(path.with_suffix(".manifest.json").read_text())
        if receipt["sha256"] != file_hash(path) or receipt["spec"] != spec:
            raise ValueError(f"Provenance check failed for {path}")
        receipts[name] = receipt
        for row in read_jsonl(path):
            task = normalize(row, name, spec)
            if name in research_pool:
                task.official_holdout = False
            fp = digest([task.kind, task.repo, " ".join(task.prompt.split())])
            key = fingerprint_ids.get(fp, task.task_id)
            fingerprint_ids[fp] = key
            aliases[task.task_id] = key
            task.group_id = key
            task.task_id = key
            previous = tasks.get(key)
            if previous:
                holdout = previous.official_holdout or task.official_holdout
                if task.official_holdout or "verified" in name:
                    tasks[key] = task
                tasks[key].official_holdout = holdout
            else:
                tasks[key] = task
    if not tasks:
        raise ValueError("No downloaded datasets found; run data download first")
    assignments = {}
    strata = defaultdict(list)
    for key, task in tasks.items():
        if task.official_holdout:
            assignments[key] = "test"
        else:
            strata[(task.kind, task.repo)].append(key)
    for keys in strata.values():
        keys.sort(key=lambda key: digest([seed, key]))
        start, cumulative = 0, 0.0
        for split, fraction in SPLITS:
            cumulative += fraction
            end = round(cumulative * len(keys))
            for key in keys[start:end]:
                assignments[key] = split
            start = end
    roles = {}
    calib = sorted(
        (k for k, s in assignments.items() if s == "calib"),
        key=lambda key: digest([seed, "inner-calibration", key]),
    )
    for i, key in enumerate(calib):
        roles[key] = (
            "critic_train"
            if i < len(calib) * 0.5
            else "probability"
            if i < len(calib) * 0.75
            else "verifier_stats"
        )
    output = Path(output)
    if (output / "manifest.json").exists():
        raise ValueError("Prepared data is immutable; use a new output directory")
    output.mkdir(parents=True, exist_ok=True)
    write_jsonl(output / "tasks.jsonl", (tasks[k].model_dump(mode="json") for k in sorted(tasks)))
    mapping = {k: {"split": assignments[k], "calibration_role": roles.get(k)} for k in tasks}
    write_json(output / "splits.json", mapping)
    report = {
        "seed": seed,
        "research_pool_sources": sorted(research_pool),
        "unique_tasks": len(tasks),
        "counts": dict(Counter(assignments.values())),
        "sources": receipts,
        "aliases": aliases,
        "tasks_sha256": file_hash(output / "tasks.jsonl"),
        "splits_sha256": file_hash(output / "splits.json"),
        "note": "10/25/20/35/10 within non-holdout strata; official holdouts forced to test",
    }
    write_json(output / "manifest.json", report)
    return report


def load_tasks(directory, split=None, source=None, limit=None):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    for filename, field in [("tasks.jsonl", "tasks_sha256"), ("splits.json", "splits_sha256")]:
        if file_hash(directory / filename) != manifest[field]:
            raise ValueError(f"Prepared dataset integrity failure: {filename}")
    assignments = json.loads((directory / "splits.json").read_text())
    count = 0
    for row in read_jsonl(directory / "tasks.jsonl"):
        task = Task.model_validate(row)
        assignment = assignments[task.group_id]
        if split and assignment["split"] != split:
            continue
        if source and task.source != source:
            continue
        yield task, assignment
        count += 1
        if limit is not None and count >= limit:
            break
