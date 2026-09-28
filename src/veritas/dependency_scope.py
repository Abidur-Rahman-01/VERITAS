"""Public-only, development-only screening for the interface/caller pilot.

Hints are navigation aids, never eligibility labels or evidence of interactions.
"""

import re
from collections import Counter
from pathlib import Path

from .data import load_tasks
from .io import digest, file_hash, write_json, write_jsonl

HINTS = {
    "interface": r"\b(?:interface|signature|parameter|argument|return(?:s|ed)?|contract)\b",
    "caller": r"\b(?:caller|callers|call\s+site|calling|backward.compatib\w*)\b",
}


def scope_spec():
    return {
        "schema_version": 1,
        "family": "python_function_interface_and_callers",
        "stage": "public_development_screening",
        "split": "dev",
        "include": [
            "Public issue requests a function-interface or return-contract repair",
            "Pinned base repository supports Python interface/caller inspection",
            "Target function and potential caller can be identified from public evidence",
        ],
        "exclude": ["Non-SWE tasks", "Official holdouts", "Non-development assignments"],
        "review_rules": [
            "All eligible-source development SWE issues enter the queue, even without hints",
            "Hints are not eligibility decisions; ambiguous evidence remains uncertain",
            "Use public issue and pinned base code only, never reference patches or outcomes",
            "Independent review and adjudication precede publication cohort finalization",
        ],
        "hint_patterns": HINTS,
        "review_statuses": ["pending", "include", "exclude", "uncertain"],
    }


def screen_row(task, assignment):
    """Explicit allowlist prevents private reference data entering reviewer artifacts."""
    if task.kind != "swe" or task.official_holdout or assignment.get("split") != "dev":
        return None
    hints = {
        name: sorted({m.group(0).lower() for m in re.finditer(pattern, task.prompt, re.I)})
        for name, pattern in HINTS.items()
    }
    public = task.model_dump(mode="json", exclude={"private"})
    return {
        "task_id": task.task_id,
        "group_id": task.group_id,
        "source": task.source,
        "source_revision": task.source_revision,
        "repo": task.repo,
        "base_commit": task.base_commit,
        "split": "dev",
        "prompt": task.prompt,
        "public_task_sha256": digest(public),
        "screening_hints": hints,
        "review": {
            "status": "pending",
            "reviewer": None,
            "reason": None,
            "public_evidence": [],
            "target_path": None,
            "target_symbol": None,
            "caller_evidence": [],
        },
    }


def create_scope(tasks, output, source=None):
    tasks, output = Path(tasks), Path(output)
    if output.exists():
        raise ValueError("Scope output already exists; use a new directory to preserve provenance")
    rows = []
    excluded = Counter()
    for task, assignment in load_tasks(tasks, split="dev", source=source):
        row = screen_row(task, assignment)
        if row is None:
            excluded["official_holdout" if task.official_holdout else "non_swe"] += 1
        else:
            rows.append(row)
    rows.sort(key=lambda row: row["task_id"])
    if not rows:
        raise ValueError("No non-holdout development SWE tasks in the requested source")
    if len({row["task_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate task IDs in scope inputs")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "scope.json", scope_spec())
    write_jsonl(output / "review_queue.jsonl", rows)
    manifest = {
        "schema_version": 1,
        "status": "awaiting_independent_scope_review",
        "source_filter": source,
        "input_hashes": {
            name: file_hash(tasks / name)
            for name in ("manifest.json", "tasks.jsonl", "splits.json")
        },
        "artifact_hashes": {
            name: file_hash(output / name) for name in ("scope.json", "review_queue.jsonl")
        },
        "implementation_sha256": file_hash(Path(__file__)),
        "queued_tasks": len(rows),
        "task_groups": len({row["group_id"] for row in rows}),
        "repositories": dict(sorted(Counter(row["repo"] or "unknown" for row in rows).items())),
        "excluded_development_tasks": dict(sorted(excluded.items())),
        "inference_started": False,
        "cohort_finalized": False,
    }
    write_json(output / "manifest.json", manifest)
    return manifest
