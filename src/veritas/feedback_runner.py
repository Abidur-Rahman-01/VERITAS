"""
End-to-end execution engine for paired feedback-selection study.

Runs each planned block:
1. Initialize clean workspace from repository baseline.
2. Run common parent draft phase; save parent patch and session history.
3. Privately grade parent draft (parent_resolved: True/False).
4. On development repositories, run five arms; on confirmation repositories, run only adaptive
   and the fixed arm selected and frozen on development:
   a. Clone parent workspace and history into branch directory.
   b. Instantiate FeedbackCheckpointController with evidence producer.
   c. Run initial checkpoint on parent patch.
   d. Execute revision continuation with equal resource budget.
   e. Freeze final patch and grade independently in clean environment.
   f. Record result with total credits, resolution, and audit metadata.
5. Append result rows to results.jsonl for confirmatory paired analysis.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

# The CLI entry point installed by `uv sync` runs with the environment's
# executable directory on sys.path, not necessarily the checkout root. The
# Docker grading helpers live in scripts/, so expose the checkout before
# importing them.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from .config import ModelConfig, SandboxConfig
from .feedback_evidence import EvidenceItem, PatchCheckpoint, tool_observation_item
from .feedback_policy import ARMS
from .feedback_runtime import FeedbackCheckpointController
from .feedback_study import analyze_results, verify_frozen_baseline, verify_plan
from .io import digest, file_hash, read_jsonl, write_json, write_text
from .models import LocalModel
from .runtime import AgentSession, CreditBudget, CreditBudgetExceeded, run_phase
from .sandbox import DockerSandbox, LocalSandbox, make_patch
from .schema import Task
from .state import tree_hash
from .store import EventStore
import stat
from scripts.veritas_cloud_worker import run_cmd

def safe_rmtree(p: Path | str):
    p = Path(p)
    if not p.exists():
        return
    def on_exc(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass
    shutil.rmtree(p, onerror=on_exc)



def get_task_setup_fn(task: Task | str) -> Callable[[Path], tuple[str, str]]:
    """Resolve task setup function from task across SWE-rebench-V2 and fixtures."""
    if isinstance(task, Task) and (
        task.private.get("image_name") or task.private.get("docker_image")
    ):
        image_name = task.private.get("image_name") or task.private.get("docker_image")
        def setup_container_task(ws: Path) -> tuple[str, str]:
            from .sandbox import initialize_swe_workspace

            initialize_swe_workspace(image_name, ws, task.base_commit)
            return task.repo or "repo", task.prompt
        return setup_container_task

    task_id = task.task_id if isinstance(task, Task) else str(task)
    clean_id = task_id.replace("swe:", "")
    from scripts.run_action_time_tse_experiment import TASK_REGISTRY
    if clean_id in TASK_REGISTRY:
        return TASK_REGISTRY[clean_id]
    for candidate in [clean_id, f"swe_{clean_id}", f"repo_{clean_id}"]:
        if candidate in TASK_REGISTRY:
            return TASK_REGISTRY[candidate]
    raise ValueError(f"No setup function registered for task: {task_id}")

def evaluate_task(task: Task, ws: Path, baseline: Path, grade_directory: Path,
                  grader_spec=None) -> dict:
    """Grade independently and retain status, log, and grading wall time."""
    started = time.monotonic()
    image_name = task.private.get("image_name") or task.private.get("docker_image")
    if image_name:
        if grader_spec is None:
            raise RuntimeError("Image-backed benchmark task has no pinned official grader configuration")
        from .awareness_grading import grade_patch

        if Path(grade_directory).exists():
            safe_rmtree(grade_directory)
        patch = make_patch(baseline, ws)
        grade = grade_patch(
            task=task, patch=patch, spec=grader_spec, directory=grade_directory,
            opaque_id=digest([task.task_id, digest(patch), grade_directory.name])[:20],
        )
        harness_log = grade_directory / "harness.log"
        log = harness_log.read_text(errors="replace")[-4000:] if harness_log.is_file() else ""
        return {"resolved": grade.get("resolved"), "status": grade["status"],
                "log": grade.get("error") or log, "seconds": grade.get("seconds", time.monotonic() - started),
                "grader_identity": grade.get("harness_identity"),
                "grader_package_sha256": grade.get("harness_package_sha256"),
                "report_hash": grade.get("report_hash")}
    resolved, output = evaluate_workspace(ws)
    status = "resolved" if resolved else (
        "infrastructure_error" if "Evaluation error:" in output or "Evaluation timed out" in output
        else "unresolved"
    )
    return {"resolved": None if status == "infrastructure_error" else resolved,
            "status": status, "log": output, "seconds": time.monotonic() - started}

def evaluate_workspace(ws: Path) -> tuple[bool, str]:
    """Independent grading: execute pytest in the isolated workspace."""
    if importlib.util.find_spec("pytest") is None:
        return False, "Evaluation error: pytest is not installed in the active Python environment"
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q"],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (res.stdout or "") + "\n" + (res.stderr or "")
        return res.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Evaluation timed out after 30 seconds"
    except Exception as exc:
        return False, f"Evaluation error: {exc}"


def make_task_sandbox(task: Task, workspace: Path, fallback: SandboxConfig):
    """Run SWE-rebench actors in their task image; use local only for fixtures."""
    image_name = task.private.get("image_name") or task.private.get("docker_image")
    if image_name:
        cfg = SandboxConfig(
            image=image_name,
            platform=fallback.platform,
            memory=fallback.memory,
            cpus=fallback.cpus,
            timeout_seconds=fallback.timeout_seconds,
            max_output_chars=fallback.max_output_chars,
        )
        return DockerSandbox(workspace, cfg)
    return LocalSandbox(workspace, fallback)


def make_evidence_producer(task: Task, baseline: Path | None = None,
                           credit_budget: CreditBudget | None = None):
    """Produce only public, actor-visible evidence for a treatment branch.

    Private test patches, FAIL_TO_PASS identifiers, and independent grader
    outcomes are outcome-plane data. They must never enter the evidence packets.
    """
    def produce_impl(checkpoint: PatchCheckpoint, workspace: Path, record, session) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        # The public task statement is shared context, not a hidden label.
        items.append(EvidenceItem.create(
            task_id=checkpoint.task_id, branch_id=checkpoint.branch_id,
            checkpoint_id=checkpoint.checkpoint_id, source="issue", basis="public_statement",
            patch_hash=checkpoint.patch_hash, tree_hash=checkpoint.tree_hash,
            environment_hash=checkpoint.environment_hash,
            raw_artifact_hash=digest(task.prompt), claim=task.prompt[:1600],
            affected_files=checkpoint.changed_files, cost_credits=0.0,
        ))

        # Public static checks only: never apply the benchmark's hidden test
        # patch or use its FAIL_TO_PASS/PASS_TO_PASS labels during treatment.
        diff_result = subprocess.run(
            ["git", "diff", "--check", "HEAD"], cwd=workspace,
            capture_output=True, text=True, timeout=15, check=False,
        )
        diff_output = ((diff_result.stdout or "") + (diff_result.stderr or "")).strip()
        items.append(EvidenceItem.create(
            task_id=checkpoint.task_id, branch_id=checkpoint.branch_id,
            checkpoint_id=checkpoint.checkpoint_id, source="static", basis="observed",
            patch_hash=checkpoint.patch_hash, tree_hash=checkpoint.tree_hash,
            environment_hash=checkpoint.environment_hash,
            command="git diff --check HEAD", raw_artifact_hash=digest(diff_output),
            claim=(f"git diff --check reported: {diff_output[:1000]}" if diff_result.returncode
                   else "git diff --check passed."),
            observed=diff_output or f"exit code {diff_result.returncode}",
            affected_files=checkpoint.changed_files, cost_credits=0.0,
        ))

        # Syntax-check only changed Python files. This observes public source
        # files and does not invoke the benchmark grader or test metadata.
        for rel_path in checkpoint.changed_files:
            target_file = workspace / rel_path
            if target_file.suffix == ".py" and target_file.is_file():
                try:
                    compile(target_file.read_text(encoding="utf-8", errors="replace"), rel_path, "exec")
                except SyntaxError as se:
                    items.append(EvidenceItem.create(
                        task_id=checkpoint.task_id, branch_id=checkpoint.branch_id,
                        checkpoint_id=checkpoint.checkpoint_id, source="static", basis="observed",
                        patch_hash=checkpoint.patch_hash, tree_hash=checkpoint.tree_hash,
                        environment_hash=checkpoint.environment_hash,
                        raw_artifact_hash=digest(str(se)),
                        claim=f"SyntaxError in {rel_path}: {se.msg} at line {se.lineno}",
                        location=f"{rel_path}:{se.lineno}", observed=str(se),
                        affected_files=[rel_path], cost_credits=0.1,
                    ))

        # Capture a public tool observation when this action also changed the
        # patch. Read/test outputs without a tree change are handled by the
        # controller at the existing checkpoint.
        if record is not None and getattr(record, "executed", False) and record.action:
            proposal_dict = record.action.proposal.model_dump(mode="json")
            items.append(tool_observation_item(checkpoint, proposal_dict, record.observation, record.step_id))

        return items

    def produce(checkpoint: PatchCheckpoint, workspace: Path, record, session) -> list[EvidenceItem]:
        started = time.monotonic()
        try:
            return produce_impl(checkpoint, workspace, record, session)
        finally:
            if credit_budget is not None:
                credit_budget.charge_tool(time.monotonic() - started)
    return produce


def preflight_task_images(tasks: list[Task], *, allow_local_fixtures: bool) -> dict:
    """Validate grader provenance and make all pinned images available upfront."""
    missing = [task.task_id for task in tasks
               if not (task.private.get("image_name") or task.private.get("docker_image"))]
    if missing and not allow_local_fixtures:
        sample = ", ".join(missing[:5])
        raise ValueError(
            f"Benchmark preflight failed: {len(missing)} task(s) lack image_name/docker_image "
            f"(examples: {sample}). Refusing the local fixture fallback."
        )
    if missing and importlib.util.find_spec("pytest") is None:
        raise RuntimeError("Explicit local-fixture runs require pytest in the active environment")
    image_tasks = [task for task in tasks
                   if task.private.get("image_name") or task.private.get("docker_image")]
    grader_fields = ("FAIL_TO_PASS", "PASS_TO_PASS", "test_patch")
    malformed = [task.task_id for task in image_tasks
                 if not all(key in task.private for key in grader_fields)]
    if malformed:
        raise ValueError(
            f"Benchmark preflight failed: {len(malformed)} image-backed task(s) lack official "
            "grader fields. Re-prepare the cohort with "
              "pinned SWE-rebench metadata."
        )
    if not image_tasks:
        return {"grader": None, "images": {}}
    if any(task.source != "swe_rebench" for task in image_tasks):
        raise ValueError("Image-backed feedback studies currently require canonical swe_rebench tasks")
    from .awareness_grading import harness_fingerprint

    grader_fingerprint = harness_fingerprint(sys.executable)
    grader_commit = (grader_fingerprint.get("origin") or {}).get("vcs_info", {}).get("commit_id")
    expected_commit = "d307ff9f2168a0448843c0d5881d2cd498d9f73f"
    if grader_commit != expected_commit:
        raise ValueError(
            "Official grader mismatch: expected the pinned SWE-rebench fork at "
            f"{expected_commit}, found {grader_commit or 'unknown'}. Run via .venv-rebench/bin/veritas."
        )
    docker_code, _, docker_err = run_cmd(["docker", "info"], timeout=20)
    if docker_code != 0:
        raise RuntimeError(f"Docker is unavailable before actor execution: {docker_err[:500]}")
    images = sorted({task.private.get("image_name") or task.private.get("docker_image")
                     for task in image_tasks})
    image_identities = {}
    host_arch = {"x86_64": "amd64", "AMD64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(
        platform.machine(), platform.machine()
    )
    expected_platform = f"linux/{host_arch}"
    for image in images:
        inspect_code, _, inspect_err = run_cmd(["docker", "image", "inspect", image], timeout=20)
        if inspect_code != 0:
            print(f"  [Preflight] Pulling pinned task image {image}...", flush=True)
            pull_code, _, pull_err = run_cmd(["docker", "pull", image], timeout=1800)
            if pull_code != 0:
                raise RuntimeError(f"Failed to pull pinned task image {image}: {pull_err[:500]}")
            inspect_code, _, inspect_err = run_cmd(["docker", "image", "inspect", image], timeout=20)
            if inspect_code != 0:
                raise RuntimeError(f"Pinned image unavailable after pull {image}: {inspect_err[:500]}")
        inspect_code, inspect_out, inspect_err = run_cmd([
            "docker", "image", "inspect", image, "--format", "{{.Id}}|{{.Os}}/{{.Architecture}}"
        ], timeout=20)
        if inspect_code != 0:
            raise RuntimeError(f"Could not fingerprint pinned image {image}: {inspect_err[:500]}")
        image_id, image_platform = inspect_out.strip().split("|", 1)
        if image_platform != expected_platform:
            raise RuntimeError(
                f"Pinned task image {image} is {image_platform}; this study requires {expected_platform}"
            )
        image_identities[image] = {"image_id": image_id, "platform": image_platform}
    return {
        "grader": {"commit": grader_commit, "package_sha256": grader_fingerprint["sha256"],
                   "identity": f"swe-rebench-fork@{grader_commit}", "python": sys.executable,
                   "platform": expected_platform},
        "images": image_identities,
    }


def execute_study(
    study_dir: str | Path,
    *,
    actor_model_name: str = "qwen2.5-coder:7b",
    draft_steps: int = 4,
    revision_steps: int = 6,
    budget_credits: float = 30.0,
    resume: bool = True,
    task_limit: int | None = None,
    partition: str = "development",
    parents_only: bool = False,
    allow_local_fixtures: bool = False,
) -> dict:
    """Execute all planned blocks and branches of a verified study plan."""
    study_root = Path(study_dir).resolve()
    verify_plan(study_root)
    if budget_credits <= 0:
        raise ValueError("--budget must be positive")
    if partition not in {"development", "confirmation"}:
        raise ValueError("partition must be development or confirmation; stages cannot be combined")
    if parents_only and partition != "confirmation":
        raise ValueError("--parents-only is only valid for the confirmation partition")
    if partition == "confirmation" and task_limit is not None:
        raise ValueError("Confirmation screening and treatment must cover the full frozen partition")
    study_protocol = json.loads((study_root / "protocol.json").read_text(encoding="utf-8"))
    expected_env = study_protocol.get("environment_mode", "pinned_images")
    if expected_env == "local_fixtures" and not allow_local_fixtures:
        raise ValueError("This plan is explicitly marked local_fixtures; pass --allow-local-fixtures to run it")
    if expected_env == "pinned_images" and allow_local_fixtures:
        raise ValueError("--allow-local-fixtures cannot downgrade a pinned-image study")
    tasks_by_id = {row["task_id"]: Task.model_validate(row)
                   for row in read_jsonl(study_root / "tasks.jsonl")}
    preflight = preflight_task_images(
        list(tasks_by_id.values()), allow_local_fixtures=allow_local_fixtures
    )
    grader_spec = None
    if preflight["grader"]:
        from .awareness import GraderSpec

        grader_spec = GraderSpec(
            python=preflight["grader"]["python"],
            identity=preflight["grader"]["identity"],
            namespace="none",
            timeout_seconds=1800,
            max_attempts=1,
            package_sha256=preflight["grader"]["package_sha256"],
            platform=preflight["grader"]["platform"],
        )

    implementation_files = [
        Path(__file__), Path(__file__).with_name("feedback_study.py"),
        Path(__file__).with_name("awareness_grading.py"),
        Path(__file__).with_name("awareness.py"),
        Path(__file__).with_name("feedback_policy.py"),
        Path(__file__).with_name("feedback_runtime.py"),
        Path(__file__).with_name("feedback_evidence.py"),
        Path(__file__).with_name("runtime.py"), Path(__file__).with_name("models.py"),
        Path(__file__).with_name("sandbox.py"), REPO_ROOT / "scripts" / "veritas_cloud_worker.py",
    ]
    execution_protocol = {
        "schema_version": 1,
        "study": "veritas-feedback-selection-confirmatory-v2",
        "pilot_status": "staged_repository_disjoint_study",
        "plan_hash": json.loads((study_root / "plan.json").read_text())["plan_hash"],
        "actor": {"name": actor_model_name, "backend": "ollama",
                  "base_url": "http://localhost:11434", "max_tokens_per_call": 2048,
                  "temperature": 0.2, "context_tokens": 8192},
        "phase_limits": {"draft_steps": draft_steps, "draft_completion_tokens": 4096,
                         "draft_seconds": 180, "revision_steps": revision_steps,
                         "revision_completion_tokens": 8192, "revision_seconds": 300},
        "budget_mode": "hard_per_task_total_credit_cap_including_common_parent_actor_and_tool_usage",
        "budget_scope": "model tokens, actor tools, public evidence checks, and selector credits; excludes image setup and private outcome grading",
        "total_credit_cap_per_task_arm": budget_credits,
        "credit_formula": "(prompt_tokens + completion_tokens) * 0.002 + measured_tool_seconds * 0.05 + selector_credits",
        "budget_reservation": {"context_tokens": 8192, "minimum_completion_tokens": 256,
                               "max_actor_tool_seconds": 30,
                               "max_evidence_seconds": 15},
        "environment_mode": expected_env,
        "official_grader": preflight["grader"],
        "pinned_docker_images": preflight["images"],
        "evidence_sources": ["public_issue", "git_diff_check", "changed_python_syntax", "actor_tool_observations"],
        "private_grading_data_available_to_actor_or_selector": False,
        "branch_execution_order": "deterministic hash-randomized within each task block",
        "implementation_sha256": {p.name: file_hash(p) for p in implementation_files},
        "platform": platform.platform(),
    }
    execution_protocol_path = study_root / "execution_protocol.json"
    if execution_protocol_path.exists():
        existing_protocol = json.loads(execution_protocol_path.read_text(encoding="utf-8"))
        if existing_protocol != execution_protocol:
            raise ValueError(
                "Execution settings or implementation changed since this study began; "
                "create a new study directory instead of mixing protocols"
            )
    else:
        write_json(execution_protocol_path, execution_protocol)

    blocks = list(read_jsonl(study_root / "blocks.jsonl"))
    branches_by_block = {}
    for branch in read_jsonl(study_root / "branches.jsonl"):
        branches_by_block.setdefault(branch["block_id"], []).append(branch)

    results_file = study_root / "results.jsonl"
    existing_results: set[tuple[str, str]] = set()
    if results_file.exists() and resume:
        for r in read_jsonl(results_file):
            existing_results.add((r["block_id"], r["arm"]))

    # Prepare actor model
    model_cfg = ModelConfig(
        name=actor_model_name,
        backend="ollama",
        base_url="http://localhost:11434",
        max_tokens=2048,
        temperature=0.2,
    )
    actor_model = LocalModel(model_cfg)

    sandbox_cfg = SandboxConfig(timeout_seconds=30)
    protocol_stub = SimpleNamespace(
        compact=False,
        history_chars=16000,
        observation_chars=4000,
        input_chars=32000,
        partition=partition,
        sandbox=sandbox_cfg,
    )
    draft_limits = SimpleNamespace(steps=draft_steps, completion_tokens=4096, seconds=180.0)
    revision_limits = SimpleNamespace(steps=revision_steps, completion_tokens=8192, seconds=300.0)

    blocks_executed = 0
    branches_executed = 0

    blocks = [block for block in blocks if block.get("partition") == partition]
    if task_limit:
        blocks = blocks[:task_limit]

    if partition == "confirmation":
        frozen_baseline = verify_frozen_baseline(study_root)
        minimum_incorrect = int(study_protocol.get("minimum_confirmation_incorrect", 0))
        confirmation_lock = {
            "plan_hash": json.loads((study_root / "plan.json").read_text())["plan_hash"],
            "frozen_baseline_hash": frozen_baseline["content_hash"],
            "minimum_confirmation_incorrect": minimum_incorrect,
            "primary_comparison": ["adaptive", frozen_baseline["selected_fixed_arm"]],
        }
        lock_path = study_root / "confirmation_lock.json"
        if lock_path.exists():
            if json.loads(lock_path.read_text(encoding="utf-8")) != confirmation_lock:
                raise ValueError("Confirmation protocol differs from the frozen confirmation lock")
        else:
            write_json(lock_path, confirmation_lock)
        if not parents_only and minimum_incorrect < 1:
            raise ValueError("Plan must predeclare --min-confirmation-incorrect before confirmation branches run")
        if not parents_only:
            incorrect_parent_count = 0
            for block in blocks:
                grade_path = study_root / "blocks" / block["block_id"] / "parent_grade.json"
                if not grade_path.is_file():
                    raise ValueError("Run confirmation with --parents-only first; a parent grade is missing")
                grade = json.loads(grade_path.read_text(encoding="utf-8"))
                if grade.get("parent_resolved") not in (True, False):
                    raise ValueError(
                        f"Confirmation parent grade is unknown for {block['task_id']}; fix grader "
                        "infrastructure before opening treatment branches."
                    )
                incorrect_parent_count += grade.get("parent_resolved") is False
            if incorrect_parent_count < minimum_incorrect:
                raise ValueError(
                    f"Confirmation gate failed: {incorrect_parent_count} initially incorrect parents; "
                    f"the plan predeclares {minimum_incorrect}. Increase the cohort under a new plan; "
                    "do not lower the threshold after observing outcomes."
                )
    else:
        frozen_baseline = None

    print(f"\n=======================================================")
    print(f"VERITAS End-to-End Feedback Study Executor")
    print(f"Study: {study_root.name}")
    branch_count = 0 if parents_only else (2 if partition == "confirmation" else len(ARMS))
    print(f"Blocks: {len(blocks)} | Branches per block: {branch_count}")
    print(f"Actor Model: {actor_model_name}")
    print(f"Partition: {partition}{' (parent screening only)' if parents_only else ''}")
    print(f"Total per-task-arm credit cap: {budget_credits} (hard enforced with conservative reservations)")
    print(f"Matched phase limits: draft steps={draft_steps}, revision steps={revision_steps}")
    print(f"=======================================================\n")

    for block_idx, block in enumerate(blocks, start=1):
        block_id = block["block_id"]
        task_id = block["task_id"]
        task = tasks_by_id[task_id]
        setup_fn = get_task_setup_fn(task)

        block_dir = study_root / "blocks" / block_id
        block_dir.mkdir(parents=True, exist_ok=True)

        print(f"[{block_idx}/{len(blocks)}] Block {block_id[:10]} (Task: {task_id}, Repo: {task.repo}, Partition: {block['partition']})")

        # Check if all branches of this block are already done
        planned_branches = branches_by_block.get(block_id, [])
        selected_arms = ({"adaptive", frozen_baseline["selected_fixed_arm"]}
                         if partition == "confirmation" else set(ARMS))
        relevant_branches = [b for b in planned_branches if b["arm"] in selected_arms]
        all_done = bool(relevant_branches) and all(
            (block_id, b["arm"]) in existing_results for b in relevant_branches
        )
        if all_done and resume:
            print("  -> All required branches already completed. Skipping block.")
            continue

        # Common parent draft setup
        parent_workspace = block_dir / "parent_workspace"
        parent_baseline = block_dir / "parent_baseline"
        parent_grade_file = block_dir / "parent_grade.json"
        parent_session_file = block_dir / "parent_session.json"

        if not (parent_workspace.exists() and parent_grade_file.exists()):
            # Run clean setup for common parent draft
            if parent_workspace.exists():
                safe_rmtree(parent_workspace)
            if parent_baseline.exists():
                safe_rmtree(parent_baseline)

            _, _ = setup_fn(parent_workspace)
            shutil.copytree(parent_workspace, parent_baseline)

            parent_session = AgentSession()
            parent_store = EventStore(block_dir / "draft_events.sqlite")
            parent_sandbox = make_task_sandbox(task, parent_workspace, sandbox_cfg)
            parent_budget = CreditBudget(cap=budget_credits)

            print(f"  [Draft] Running common parent draft with actor...")
            draft_res = run_phase(
                task=task,
                session=parent_session,
                model=actor_model,
                sandbox=parent_sandbox,
                store=parent_store,
                output=str(block_dir),
                trial_id=f"draft_{block_id}",
                actor_name=actor_model_name,
                phase="draft",
                limits=draft_limits,
                protocol=protocol_stub,
                cue="Solve the issue in the repository and run tests to verify your fix.",
                credit_budget=parent_budget,
            )
            parent_store.close()

            parent_patch = make_patch(parent_baseline, parent_workspace)
            write_text(block_dir / "parent.patch", parent_patch)

            # Private parent grading (hidden from all treatment arms)
            parent_grade = evaluate_task(
                task, parent_workspace, parent_baseline,
                block_dir / "parent_official_grade", grader_spec,
            )
            parent_resolved = parent_grade["resolved"]
            parent_grade_data = {
                "parent_resolved": parent_resolved,
                "grader_status": parent_grade["status"],
                "grader_identity": parent_grade.get("grader_identity"),
                "grader_package_sha256": parent_grade.get("grader_package_sha256"),
                "grader_report_hash": parent_grade.get("report_hash"),
                "grader_seconds": parent_grade["seconds"],
                "output": parent_grade["log"][:1000],
                "patch_hash": digest(parent_patch),
                "tree_hash": tree_hash(parent_workspace),
                "parent_credits": parent_budget.spent,
                "parent_prompt_tokens": draft_res.get("prompt_tokens", 0),
                "parent_completion_tokens": draft_res.get("known_completion_tokens", 0),
                "parent_usage_complete": draft_res.get("usage_complete", False),
                "parent_tool_seconds": parent_budget.tool_seconds,
                "draft_termination": draft_res.get("termination"),
            }
            write_json(parent_grade_file, parent_grade_data)
            write_json(parent_session_file, {
                "step": parent_session.step,
                "history": parent_session.history,
            })
            parent_label = ("RESOLVED" if parent_resolved is True else
                            "INCORRECT" if parent_resolved is False else "GRADER ERROR")
            print(f"  [Draft] Completed. Private parent grade: {parent_label}")
        else:
            parent_grade_data = json.loads(parent_grade_file.read_text(encoding="utf-8"))
            parent_resolved = parent_grade_data["parent_resolved"]
            if "parent_credits" not in parent_grade_data:
                raise ValueError("Parent record lacks budget accounting; create a fresh study directory")
            parent_session_data = json.loads(parent_session_file.read_text(encoding="utf-8"))
            parent_session = AgentSession(
                step=parent_session_data["step"],
                history=parent_session_data["history"],
            )
            parent_patch = (block_dir / "parent.patch").read_text(encoding="utf-8") if (block_dir / "parent.patch").exists() else ""
            print(f"  [Draft] Reused existing parent draft (parent_resolved={parent_resolved})")

        if parent_resolved not in (True, False):
            raise RuntimeError(
                f"Parent grader did not return a valid benchmark outcome for {task_id} "
                f"(status={parent_grade_data.get('grader_status')}); refusing to run feedback arms."
            )

        if not parents_only:
            parent_credits = float(parent_grade_data["parent_credits"])
            minimum_revision_reserve = (
                (8192 + 256) * 0.002 + 60 * 0.05 + 0.25
            )
            if budget_credits - parent_credits < minimum_revision_reserve:
                raise RuntimeError(
                    f"Task {task_id} used {parent_credits:.3f} credits in the common draft, "
                    f"leaving less than the {minimum_revision_reserve:.3f}-credit safe "
                    "minimum for one revision request. Increase --budget in a fresh study."
                )
        if parents_only:
            blocks_executed += 1
            print("  [Confirmation] Parent grade recorded; treatment branches deferred.")
            continue

        # Execute the 5 treatment arms from the exact same parent state
        # Deterministically randomize execution order within each block to reduce
        # systematic time/order effects while preserving frozen assignments.
        for branch in sorted(
            relevant_branches, key=lambda row: digest([block_id, "execution-order", row["arm"]])
        ):
            arm = branch["arm"]
            branch_id = branch["branch_id"]

            if (block_id, arm) in existing_results and resume:
                print(f"    - Arm {arm:18s}: already recorded, skipping.")
                continue

            print(f"    - Arm {arm:18s}: starting paired continuation from parent...")
            branch_dir = block_dir / arm
            if branch_dir.exists():
                safe_rmtree(branch_dir)
            branch_dir.mkdir(parents=True, exist_ok=True)

            branch_workspace = branch_dir / "workspace"
            branch_baseline = branch_dir / "baseline"
            shutil.copytree(parent_workspace, branch_workspace)
            shutil.copytree(parent_baseline, branch_baseline)

            branch_session = AgentSession(
                step=parent_session.step,
                history=copy.deepcopy(parent_session.history),
            )
            branch_events: list[dict] = []
            events_jsonl = branch_dir / "events.jsonl"

            parent_credits = float(parent_grade_data["parent_credits"])
            branch_budget = CreditBudget(
                cap=budget_credits, spent=parent_credits,
                tool_seconds=float(parent_grade_data.get("parent_tool_seconds", 0.0)),
            )
            evidence_producer = make_evidence_producer(task, parent_baseline, branch_budget)

            selector_spend = 0.0

            def record_branch_event(event):
                nonlocal selector_spend
                selector_spend += float(event.get("decision", {}).get("selector_credits", 0.0))
                branch_events.append(event)

            def selector_credit():
                # Selector computation charged ONLY to Arm E (adaptive)
                if arm == "adaptive":
                    branch_budget.charge(0.25)
                    return 0.25
                return 0.0

            controller = FeedbackCheckpointController(
                task_id=task.task_id,
                branch_id=branch_id,
                arm=arm,
                baseline=branch_baseline,
                workspace=branch_workspace,
                environment_hash="local-sandbox-env",
                patch_fn=make_patch,
                evidence_producer=evidence_producer,
                packet_char_cap=6000,
                selector_credit_fn=selector_credit,
                remaining_credits_fn=lambda: branch_budget.remaining,
                event_sink=record_branch_event,
            )

            # Trigger initial checkpoint on the parent draft patch
            init_event = controller.create_initial_checkpoint(branch_session)

            branch_store = EventStore(branch_dir / "revision_events.sqlite")
            branch_sandbox = make_task_sandbox(task, branch_workspace, sandbox_cfg)

            arm_start = time.monotonic()
            rev_res = run_phase(
                task=task,
                session=branch_session,
                model=actor_model,
                sandbox=branch_sandbox,
                store=branch_store,
                output=str(branch_dir),
                trial_id=f"rev_{branch_id}",
                actor_name=actor_model_name,
                phase="revision",
                limits=revision_limits,
                protocol=protocol_stub,
                cue="Continue refining the patch using the verifier evidence.",
                on_step=controller.on_step,
                feedback_provider=controller.feedback,
                credit_budget=branch_budget,
            )
            elapsed = time.monotonic() - arm_start
            branch_store.close()

            # Record selector credits consumed during run
            selector_overhead = selector_spend
            arm_total_credits = round(branch_budget.spent, 3)

            # Freeze final patch
            final_patch = make_patch(branch_baseline, branch_workspace)
            write_text(branch_dir / "final.patch", final_patch)

            # Independent final grading
            final_grade = evaluate_task(
                task, branch_workspace, branch_baseline,
                branch_dir / "official_grade", grader_spec,
            )
            final_resolved = final_grade["resolved"]
            patch_empty = not bool(final_patch.strip())
            grader_status = "invalid_patch" if patch_empty else final_grade["status"]
            write_json(branch_dir / "grade.json", {
                "resolved": final_resolved,
                "status": grader_status,
                "output": final_grade["log"][:1000],
                "grader_seconds": final_grade["seconds"],
                "patch_hash": digest(final_patch),
                "steps": rev_res.get("steps", 0),
                "credits": arm_total_credits,
            })

            # Save checkpoint events
            with open(events_jsonl, "w", encoding="utf-8") as f:
                for ev in branch_events:
                    f.write(json.dumps(ev) + "\n")

            result_row = {
                "block_id": block_id,
                "branch_id": branch_id,
                "arm": arm,
                "task_id": task.task_id,
                "repository": task.repo,
                "partition": block["partition"],
                "resolved": final_resolved,
                "grader_status": grader_status,
                "grader_identity": final_grade.get("grader_identity"),
                "grader_package_sha256": final_grade.get("grader_package_sha256"),
                "grader_report_hash": final_grade.get("report_hash"),
                "patch_empty": patch_empty,
                "parent_resolved": parent_resolved,
                "grader_seconds": final_grade["seconds"],
                "total_credits": arm_total_credits,
                "credit_formula": "(prompt_tokens + completion_tokens) * 0.002 + tool_seconds * 0.05 + selector_credits",
                "credit_cap_enforced": True,
                "total_credit_cap": budget_credits,
                "parent_credits": round(parent_credits, 3),
                "revision_credits": round(max(0.0, branch_budget.spent - parent_credits), 3),
                "parent_prompt_tokens": parent_grade_data.get("parent_prompt_tokens", 0),
                "parent_completion_tokens": parent_grade_data.get("parent_completion_tokens", 0),
                "parent_usage_complete": parent_grade_data.get("parent_usage_complete", False),
                "parent_tool_seconds": round(float(parent_grade_data.get("parent_tool_seconds", 0.0)), 3),
                "selector_credits": round(selector_overhead, 3),
                "actor_prompt_tokens": rev_res.get("prompt_tokens", 0),
                "actor_completion_tokens": rev_res.get("known_completion_tokens", 0),
                "actor_usage_complete": rev_res.get("usage_complete", False),
                "tool_seconds": round(rev_res.get("tool_seconds", 0), 3),
                "total_tool_seconds": round(branch_budget.tool_seconds, 3),
                "revision_tool_seconds": round(max(0.0, branch_budget.tool_seconds - float(parent_grade_data.get("parent_tool_seconds", 0.0))), 3),
                "grader_backend": ("official_container" if task.private.get("image_name")
                                   or task.private.get("docker_image") else "local_fixture_pytest"),
                "steps": rev_res.get("steps", 0),
                "checkpoints": len(controller.decisions),
                "wall_seconds": round(elapsed, 2),
                "patch_hash": digest(final_patch),
            }

            with open(results_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(result_row) + "\n")
            existing_results.add((block_id, arm))
            branches_executed += 1

            status_str = (
                "GRADER ERROR (?)" if final_resolved is None else
                "EMPTY PATCH (−)" if patch_empty else
                "RESOLVED (+)" if final_resolved else "UNRESOLVED (-)"
            )
            print(f"      -> Final grade: {status_str} | Checkpoints: {len(controller.decisions)} | Credits: {arm_total_credits} | Time: {elapsed:.1f}s")

        blocks_executed += 1

    print(f"\nStudy execution finished! Blocks run: {blocks_executed}, Branches run: {branches_executed}")
    analysis = analyze_results(study_root)
    return analysis


if __name__ == "__main__":
    study_path = sys.argv[1] if len(sys.argv) > 1 else "runs/feedback_study_pilot"
    summary = execute_study(study_path)
    print("\nPaired Analysis Results:")
    print(json.dumps(summary, indent=2))
