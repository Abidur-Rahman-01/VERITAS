"""Task loading, eligibility filtering, and repository-disjoint splitting."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .config import DataConfig, SplitConfig
from .util import read_jsonl, stable_unit_interval

# SWE-bench Verified repositories whose official harness does not run plain pytest.
NON_PYTEST_VERIFIED_REPOS = frozenset({"django/django", "sympy/sympy"})
TEST_PATH = re.compile(r"(^|/)(tests?|testing)(/|$)|(^|/)test_[^/]*\.py$|_test\.py$|conftest\.py$")
DIFF_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)$", re.MULTILINE)


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    gold_patch: str
    test_patch: str
    fail_to_pass: tuple[str, ...]
    pass_to_pass: tuple[str, ...]
    image: str
    created_at: str
    source: str


def is_test_path(path: str) -> bool:
    return bool(TEST_PATH.search(path))


def patch_files(patch: str) -> list[str]:
    """Paths touched by a unified git diff (post-image path; '/dev/null' never appears here)."""
    seen: list[str] = []
    for _old, new in DIFF_HEADER.findall(patch):
        if new not in seen:
            seen.append(new)
    return seen


def _as_list(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = json.loads(value) if value.strip() else []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError("test list must be a list of strings")
    return tuple(value)


def created_at_text(value) -> str:
    """'YYYY-MM-DD HH:MM:SS' text; SWE-rebench-V2 may store Unix milliseconds."""
    if isinstance(value, (int, float)):
        moment = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        return moment.strftime("%Y-%m-%d %H:%M:%S")
    return "" if value is None else str(value)


def verified_image(instance_id: str) -> str:
    return f"swebench/sweb.eval.x86_64.{instance_id.replace('__', '_1776_')}:latest"


def task_from_row(row: dict, source: str) -> Task:
    if source in ("swe_rebench", "swe_rebench_v2"):
        image = row.get("docker_image") or row.get("image_name")
    else:
        image = verified_image(row["instance_id"])
    if not image:
        raise ValueError(f"{row.get('instance_id')}: no docker image")
    return Task(
        instance_id=row["instance_id"],
        repo=row["repo"],
        base_commit=row["base_commit"],
        problem_statement=row["problem_statement"],
        gold_patch=row["patch"],
        test_patch=row["test_patch"],
        fail_to_pass=_as_list(row.get("FAIL_TO_PASS")),
        pass_to_pass=_as_list(row.get("PASS_TO_PASS")),
        image=image,
        created_at=created_at_text(row.get("created_at")),
        source=source,
    )


def eligibility(row: dict, cfg: DataConfig, excluded: set[str]) -> str | None:
    """Return None if eligible, otherwise the reason for exclusion (recorded in the manifest)."""
    if row["instance_id"] in excluded:
        return "excluded_id"
    if cfg.created_after and created_at_text(row.get("created_at"))[:10] < cfg.created_after:
        return "before_cutoff"
    rebench = cfg.source in ("swe_rebench", "swe_rebench_v2")
    if cfg.source == "swe_rebench_v2" and str(row.get("language", "")).lower() != "python":
        return "not_python"
    if rebench and not (row.get("docker_image") or row.get("image_name")):
        return "no_prebuilt_image"
    if cfg.require_pytest_parser:
        if rebench:
            parser = (row.get("install_config") or {}).get("log_parser")
            if parser not in ("parse_log_pytest", "parse_log_pytest_v2"):
                return "non_pytest_parser"
        elif row["repo"] in NON_PYTEST_VERIFIED_REPOS:
            return "non_pytest_repo"
    if not _as_list(row.get("FAIL_TO_PASS")):
        return "no_fail_to_pass"
    source_files = [p for p in patch_files(row["patch"]) if not is_test_path(p)]
    if not source_files:
        return "no_source_change"
    if len(source_files) > cfg.max_patch_files:
        return "too_many_files"
    return None


def load_tasks(cfg: DataConfig) -> tuple[list[Task], dict]:
    excluded: set[str] = set()
    if cfg.exclude_ids_path:
        excluded = {
            line.strip()
            for line in Path(cfg.exclude_ids_path).read_text().splitlines()
            if line.strip()
        }
    reasons: Counter = Counter()
    tasks: list[Task] = []
    for row in read_jsonl(cfg.dataset_path):
        reason = eligibility(row, cfg, excluded)
        if reason:
            reasons[reason] += 1
            continue
        tasks.append(task_from_row(row, cfg.source))
    tasks.sort(key=lambda t: stable_unit_interval(cfg.sample_salt, t.instance_id))
    if cfg.max_tasks is not None:
        reasons["over_max_tasks"] += max(0, len(tasks) - cfg.max_tasks)
        tasks = tasks[: cfg.max_tasks]
    summary = {"eligible": len(tasks), "excluded": dict(sorted(reasons.items()))}
    return tasks, summary


def split_by_repository(repos: dict[str, int], cfg: SplitConfig) -> dict[str, str]:
    """Assign whole repositories to train/dev/confirm, balancing task counts deterministically.

    Repositories are visited in a salted-hash order (largest first among ties is not used, so no
    repository is privileged); each goes to the split with the largest remaining deficit.
    """
    targets = {"train": cfg.train, "dev": cfg.dev, "confirm": cfg.confirm}
    total = sum(repos.values())
    filled = {name: 0 for name in targets}
    assignment: dict[str, str] = {}
    for repo in sorted(repos, key=lambda r: stable_unit_interval(cfg.salt, r)):
        deficit = {name: targets[name] * total - filled[name] for name in targets}
        choice = max(sorted(targets), key=lambda name: deficit[name])
        assignment[repo] = choice
        filled[choice] += repos[repo]
    return assignment
