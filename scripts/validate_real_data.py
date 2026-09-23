#!/usr/bin/env python3
"""Validate downloaded originals and prepared partitions without loading any model."""

import argparse
import json
from collections import Counter
from pathlib import Path

from veritas.data import load_tasks
from veritas.io import file_hash, read_jsonl, write_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw", default="data/raw")
    p.add_argument("--prepared", default="data/prepared")
    p.add_argument("--output", default="artifacts/real-data-validation.json")
    a = p.parse_args()
    prepared = json.loads((Path(a.prepared) / "manifest.json").read_text())
    source_counts = {}
    for name, receipt in prepared["sources"].items():
        raw = Path(a.raw) / f"{name}.jsonl"
        assert file_hash(raw) == receipt["sha256"], name
        count = sum(1 for _ in read_jsonl(raw))
        assert count == receipt["rows"], name
        source_counts[name] = count
    unique, splits, kinds = set(), Counter(), Counter()
    for task, assignment in load_tasks(a.prepared):
        assert task.task_id not in unique
        unique.add(task.task_id)
        splits[assignment["split"]] += 1
        kinds[task.kind] += 1
        if task.official_holdout:
            assert assignment["split"] == "test"
        if task.source == "swe_verified":
            assert task.official_holdout
    assert len(unique) == prepared["unique_tasks"]
    result = {
        "original_source_rows": source_counts,
        "total_source_rows": sum(source_counts.values()),
        "unique_tasks": len(unique),
        "splits": dict(splits),
        "task_kinds": dict(kinds),
        "source_hashes_valid": True,
        "task_partitions_valid": True,
        "synthetic_experimental_records_generated": 0,
        "models_invoked": False,
    }
    write_json(a.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
