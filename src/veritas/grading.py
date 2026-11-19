"""Independent grading in a fresh workspace (outcome plane).

Procedure (SWE-bench semantics): start a clean container at the base commit, apply the candidate
patch, restore any test files the test patch touches, apply the test patch, run FAIL_TO_PASS and
PASS_TO_PASS by node id, and call the task resolved only if every listed test passes. Tests missing
from the report count as failed. Infrastructure problems are recorded as unknown, never as a
pass or a fail. ``validate_gold`` grades the reference patch so tasks this grader cannot reproduce
are excluded before any experiment uses them.
"""

from __future__ import annotations

import shlex
from dataclasses import asdict, dataclass, field
from typing import Callable

from .config import SandboxConfig
from .producers import parse_summary
from .sandbox import Sandbox, SandboxError, open_sandbox
from .tasks import Task, patch_files
from .util import sha256_text

PASSING = {"PASSED", "XFAIL"}
CHUNK = 150


@dataclass
class Grade:
    status: str  # resolved | unresolved | infrastructure_error | grader_error
    reason: str = ""
    fail_to_pass: dict[str, str] = field(default_factory=dict)
    pass_to_pass: dict[str, str] = field(default_factory=dict)
    log_sha256: str = ""
    patch_sha256: str = ""

    @property
    def known(self) -> bool:
        return self.status in ("resolved", "unresolved")

    @property
    def resolved(self) -> bool:
        return self.status == "resolved"

    def to_json(self) -> dict:
        return asdict(self)


def run_node_ids(sandbox: Sandbox, ids: list[str], timeout: int) -> tuple[dict[str, str], str, bool]:
    outcomes: dict[str, str] = {}
    logs: list[str] = []
    timed_out = False
    for start in range(0, len(ids), CHUNK):
        chunk = ids[start:start + CHUNK]
        command = "python -m pytest -rA -q -p no:cacheprovider --tb=no " + " ".join(
            shlex.quote(test) for test in chunk
        )
        result = sandbox.exec(command, timeout=timeout)
        logs.append(result.output)
        timed_out = timed_out or result.timed_out
        found, _ = parse_summary(result.output)
        outcomes.update(found)
    return {test: outcomes.get(test, "MISSING") for test in ids}, "\n".join(logs), timed_out


def grade_in(sandbox: Sandbox, task: Task, patch: str, timeout: int) -> Grade:
    patch_hash = sha256_text(patch)
    applied = sandbox.apply_patch(patch, "candidate")
    if applied.exit_code != 0:
        return Grade("unresolved", "patch_apply_failed", patch_sha256=patch_hash,
                     log_sha256=sha256_text(applied.output))
    sandbox.reset_files(patch_files(task.test_patch))
    tests = sandbox.apply_patch(task.test_patch, "tests")
    if tests.exit_code != 0:
        return Grade("grader_error", "test_patch_apply_failed", patch_sha256=patch_hash,
                     log_sha256=sha256_text(tests.output))
    f2p, log_a, timeout_a = run_node_ids(sandbox, list(task.fail_to_pass), timeout)
    p2p, log_b, timeout_b = run_node_ids(sandbox, list(task.pass_to_pass), timeout)
    ok = all(v in PASSING for v in f2p.values()) and all(v in PASSING for v in p2p.values())
    reason = "timeout" if (timeout_a or timeout_b) and not ok else ""
    return Grade("resolved" if ok else "unresolved", reason, f2p, p2p,
                 sha256_text(log_a + "\n" + log_b), patch_hash)


def grade(task: Task, patch: str, cfg: SandboxConfig,
          opener: Callable[[], Sandbox] | None = None) -> Grade:
    try:
        sandbox = opener() if opener else open_sandbox(cfg, task.image)
    except SandboxError as exc:
        return Grade("infrastructure_error", str(exc)[:300], patch_sha256=sha256_text(patch))
    try:
        return grade_in(sandbox, task, patch, cfg.grade_timeout_seconds)
    except SandboxError as exc:
        return Grade("infrastructure_error", str(exc)[:300], patch_sha256=sha256_text(patch))
    finally:
        sandbox.close()


def validate_gold(task: Task, cfg: SandboxConfig,
                  opener: Callable[[], Sandbox] | None = None) -> Grade:
    return grade(task, task.gold_patch, cfg, opener)
