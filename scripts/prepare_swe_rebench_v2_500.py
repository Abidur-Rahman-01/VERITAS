#!/usr/bin/env python3
"""
Prepares a frozen 500-task SWE-rebench-V2 cohort directly from the downloaded Parquet file.
Enforces:
- 100% genuine SWE-rebench-V2 tasks (zero synthetic fixtures)
- Disjoint development vs confirmation repository partitions
- Frozen task manifest with SHA256 hashes
"""

import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parent.parent
PARQUET_PATH = REPO_ROOT / "data" / "swe_rebench_v2" / "data" / "train-00000-of-00001.parquet"
OUTPUT_DIR = REPO_ROOT / "data" / "v2_cohort_500"


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def select_500_cohort(seed: int = 42, target_count: int = 500):
    random.seed(seed)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Reading Parquet: {PARQUET_PATH}")
    parquet_hash = compute_sha256(PARQUET_PATH)
    table = pq.read_table(str(PARQUET_PATH))

    # Group valid tasks by repository
    repos = defaultdict(list)
    for i in range(len(table)):
        lang = table["language"][i].as_py()
        if lang != "python":
            continue

        install_cfg = table["install_config"][i].as_py() or {}
        test_cmd = install_cfg.get("test_cmd")
        image = table["image_name"][i].as_py()
        repo = table["repo"][i].as_py()
        iid = table["instance_id"][i].as_py()
        base_commit = table["base_commit"][i].as_py()
        ftp = table["FAIL_TO_PASS"][i].as_py() or []
        ptp = table["PASS_TO_PASS"][i].as_py() or []

        if not (image and test_cmd and iid and base_commit):
            continue

        repos[repo].append({
            "instance_id": iid,
            "repo": repo,
            "base_commit": base_commit,
            "image_name": image,
            "test_cmd": test_cmd,
            "FAIL_TO_PASS": ftp,
            "PASS_TO_PASS": ptp,
            "problem_statement": table["problem_statement"][i].as_py(),
        })

    # Sort repositories by task count to select balanced repositories
    eligible_repos = [r for r, tasks in repos.items() if len(tasks) >= 5]
    random.shuffle(eligible_repos)

    half = len(eligible_repos) // 2
    dev_repo_pool = eligible_repos[:half]
    conf_repo_pool = eligible_repos[half:]

    dev_tasks = []
    conf_tasks = []

    target_per_split = target_count // 2

    # Collect 250 tasks from dev repos
    for r in dev_repo_pool:
        available = repos[r]
        take = min(len(available), 15)  # Cap per repo to maintain diversity
        dev_tasks.extend(available[:take])
        if len(dev_tasks) >= target_per_split:
            break
    dev_tasks = dev_tasks[:target_per_split]

    # Collect 250 tasks from conf repos
    for r in conf_repo_pool:
        available = repos[r]
        take = min(len(available), 15)
        conf_tasks.extend(available[:take])
        if len(conf_tasks) >= target_per_split:
            break
    conf_tasks = conf_tasks[:target_per_split]

    all_tasks = dev_tasks + conf_tasks
    dev_repos = sorted(list({t["repo"] for t in dev_tasks}))
    conf_repos = sorted(list({t["repo"] for t in conf_tasks}))

    # Assert 100% disjoint
    overlap = set(dev_repos).intersection(set(conf_repos))
    assert len(overlap) == 0, f"Disjoint split violated: {overlap}"

    # Write tasks.jsonl
    tasks_file = OUTPUT_DIR / "tasks.jsonl"
    with open(tasks_file, "w", encoding="utf-8") as f:
        for t in all_tasks:
            f.write(json.dumps(t) + "\n")

    manifest = {
        "study": "veritas-swe-rebench-v2-500",
        "dataset_source": "SWE-rebench-V2",
        "parquet_sha256": parquet_hash,
        "total_tasks": len(all_tasks),
        "split_ratio": {"development": len(dev_tasks), "confirmation": len(conf_tasks)},
        "development_repositories": dev_repos,
        "confirmation_repositories": conf_repos,
        "seed": seed,
    }

    manifest_file = OUTPUT_DIR / "manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Successfully froze 500-task cohort in {OUTPUT_DIR}:")
    print(f"  Total tasks: {len(all_tasks)}")
    print(f"  Development tasks: {len(dev_tasks)} across {len(dev_repos)} repos")
    print(f"  Confirmation tasks: {len(conf_tasks)} across {len(conf_repos)} repos")
    print(f"  Repository overlap: {len(overlap)}")
    print(f"  Tasks SHA-256: {compute_sha256(tasks_file)}")


if __name__ == "__main__":
    select_500_cohort()
