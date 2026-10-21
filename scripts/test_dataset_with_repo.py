#!/usr/bin/env python3
"""Validate the locally prepared SWE-rebench release and its task metadata.

This deliberately performs no downloads, Docker builds, model inference, or grading.
For the full harness workflow, use ``veritas swe image-map`` and the frozen study plan.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from veritas.data import load_tasks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", default="data/prepared")
    parser.add_argument("--source", default="swe_rebench")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")

    root = Path(args.tasks)
    if not (root / "manifest.json").is_file():
        parser.error(f"Prepared dataset not found: {root}; run `veritas data prepare` first")

    tasks = list(load_tasks(root, source=args.source, limit=args.limit))
    if not tasks:
        parser.error(f"No tasks found for source={args.source!r} in {root}")
    invalid = [task.task_id for task, _ in tasks if task.kind != "swe" or
               not task.repo or not task.base_commit or not task.private.get("instance_id")]
    if invalid:
        parser.error(f"SWE task metadata is incomplete for {len(invalid)} sampled task(s)")

    repos = Counter(task.repo for task, _ in tasks)
    print(f"Prepared dataset: {root}")
    print(f"Source: {args.source}")
    print(f"Validated sample: {len(tasks)} tasks, {len(repos)} repositories")
    for task, _ in tasks[: min(5, len(tasks))]:
        print(f"  {task.private['instance_id']} | {task.repo} | base={task.base_commit}")
    print("No environment images were built or grading jobs executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
