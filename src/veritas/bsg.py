"""Bug-discrimination labels for observed evidence (outcome plane; after BSG-VA).

An observed item is *bug-discriminative* if at least one of its tests has a different outcome on
the buggy base checkout than on the base checkout with the reference fix applied. Opinion items
and items whose tests exist in neither checkout get ``None`` (not applicable).
"""

from __future__ import annotations

from .grading import run_node_ids
from .sandbox import Sandbox
from .tasks import Task


def discriminative_map(task: Task, tests: list[str], open_base, timeout: int) -> dict[str, tuple]:
    """Run ``tests`` on buggy and fixed checkouts; returns test -> (buggy, fixed) outcomes."""
    if not tests:
        return {}
    buggy: Sandbox = open_base()
    try:
        before, _, _ = run_node_ids(buggy, tests, timeout)
    finally:
        buggy.close()
    fixed: Sandbox = open_base()
    try:
        applied = fixed.apply_patch(task.gold_patch, "gold")
        if applied.exit_code != 0:
            return {}
        after, _, _ = run_node_ids(fixed, tests, timeout)
    finally:
        fixed.close()
    return {t: (before[t], after[t]) for t in tests}


def label_item(item: dict, outcomes: dict[str, tuple]) -> bool | None:
    if item["basis"] != "observed" or not item.get("tests"):
        return None
    pairs = [outcomes[t] for t in item["tests"] if t in outcomes]
    pairs = [p for p in pairs if not (p[0] == "MISSING" and p[1] == "MISSING")]
    if not pairs:
        return None
    return any(before != after for before, after in pairs)
