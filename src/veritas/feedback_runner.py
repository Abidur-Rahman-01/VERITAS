"""
End-to-end execution engine for paired feedback-selection study.

Runs each planned block:
1. Initialize clean workspace from repository baseline.
2. Run common parent draft phase; save parent patch and session history.
3. Privately grade parent draft (parent_resolved: True/False).
4. For each of the 5 arms (generic_retry, raw_diagnostics, fixed_actionable, fixed_combined, adaptive):
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
from .feedback_study import analyze_results, verify_plan
from .io import digest, file_hash, read_jsonl, write_json, write_text
from .models import LocalModel
from .runtime import AgentSession, run_phase
from .sandbox import DockerSandbox, LocalSandbox, make_patch
from .schema import Task
from .state import tree_hash
from .store import EventStore
import stat
from scripts.veritas_cloud_worker import evaluate_task_in_container, run_cmd, to_container_mount_path

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
    if isinstance(task, Task) and task.source == "swe_rebench" and task.private.get("image_name"):
        image_name = task.private["image_name"]
        def setup_container_task(ws: Path) -> tuple[str, str]:
            ws.mkdir(parents=True, exist_ok=True)
            mount_ws = to_container_mount_path(ws)
            inspect_code, _, _ = run_cmd(["docker", "image", "inspect", image_name], timeout=15)
            if inspect_code != 0:
                print(f"    [Docker] Image {image_name} not local; pulling from registry...")
                pull_code, _, pull_err = run_cmd(["docker", "pull", image_name], timeout=900)
                if pull_code != 0:
                    print(f"    [Docker] Warning: Pull returned code {pull_code}: {pull_err[:300]}")
            run_cmd([
                "docker", "run", "--rm",
                "-v", f"{mount_ws}:/out_ws",
                image_name,
                "sh", "-c", "cp -a . /out_ws/ 2>/dev/null || true"
            ], timeout=180)
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

def evaluate_task(task: Task, ws: Path, baseline: Path) -> dict:
    """Grade independently and retain status, log, and grading wall time."""
    started = time.monotonic()
    if task.source == "swe_rebench" and task.private.get("image_name"):
        patch = make_patch(baseline, ws)
        res = evaluate_task_in_container(
            image_name=task.private["image_name"],
            patch=patch,
            test_patch=task.private.get("test_patch"),
            test_cmd=task.private.get("test_cmd", "pytest"),
            fail_to_pass=task.private.get("FAIL_TO_PASS", []),
            pass_to_pass=task.private.get("PASS_TO_PASS", []),
            timeout_seconds=90,
        )
        if not res.get("success"):
            return {"resolved": None, "status": "infrastructure_error",
                    "log": res.get("error", res.get("log", "Grader infrastructure failed")),
                    "seconds": res.get("duration_seconds", time.monotonic() - started)}
        resolved = bool(res.get("resolved", False))
        return {"resolved": resolved, "status": "resolved" if resolved else "unresolved",
                "log": res.get("log", ""),
                "seconds": res.get("duration_seconds", time.monotonic() - started)}
    resolved, output = evaluate_workspace(ws)
    status = "resolved" if resolved else (
        "infrastructure_error" if "Evaluation error:" in output or "Evaluation timed out" in output
        else "unresolved"
    )
    return {"resolved": None if status == "infrastructure_error" else resolved,
            "status": status, "log": output, "seconds": time.monotonic() - started}

def evaluate_workspace(ws: Path) -> tuple[bool, str]:
    """Independent grading: execute pytest in the isolated workspace."""
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
    image_name = task.private.get("image_name")
    if task.source == "swe_rebench" and image_name:
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


def make_evidence_producer(task: Task, baseline: Path | None = None):
    """Produce only public, actor-visible evidence for a treatment branch.

    Private test patches, FAIL_TO_PASS identifiers, and independent grader
    outcomes are outcome-plane data. They must never enter the evidence packets.
    """
    def produce(checkpoint: PatchCheckpoint, workspace: Path, record, session) -> list[EvidenceItem]:
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
    return produce


def execute_study(
    study_dir: str | Path,
    *,
    actor_model_name: str = "qwen2.5-coder:7b",
    draft_steps: int = 4,
    revision_steps: int = 6,
    budget_credits: float = 30.0,
    resume: bool = True,
    task_limit: int | None = None,
) -> dict:
    """Execute all planned blocks and branches of a verified study plan."""
    study_root = Path(study_dir).resolve()
    verify_plan(study_root)

    implementation_files = [
        Path(__file__), Path(__file__).with_name("feedback_study.py"),
        Path(__file__).with_name("feedback_policy.py"),
        Path(__file__).with_name("feedback_runtime.py"),
        Path(__file__).with_name("feedback_evidence.py"),
        Path(__file__).with_name("runtime.py"),
    ]
    execution_protocol = {
        "schema_version": 1,
        "study": "veritas-feedback-selection-60-pilot",
        "pilot_status": "engineering_and_descriptive_pilot_not_confirmatory",
        "plan_hash": json.loads((study_root / "plan.json").read_text())["plan_hash"],
        "actor": {"name": actor_model_name, "backend": "ollama",
                  "base_url": "http://localhost:11434", "max_tokens_per_call": 2048,
                  "temperature": 0.2, "context_tokens": 8192},
        "phase_limits": {"draft_steps": draft_steps, "draft_completion_tokens": 4096,
                         "draft_seconds": 180, "revision_steps": revision_steps,
                         "revision_completion_tokens": 8192, "revision_seconds": 300},
        "budget_mode": "matched_actor_phase_limits_resource_cost_reported_not_hard_total_cap",
        "reference_credit_cap": budget_credits,
        "credit_formula": "(prompt_tokens + completion_tokens) * 0.002 + tool_seconds * 0.05 + selector_credits",
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

    tasks_by_id = {row["task_id"]: Task.model_validate(row) for row in read_jsonl(study_root / "tasks.jsonl")}
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
        partition="development",
        sandbox=sandbox_cfg,
    )
    draft_limits = SimpleNamespace(steps=draft_steps, completion_tokens=4096, seconds=180.0)
    revision_limits = SimpleNamespace(steps=revision_steps, completion_tokens=8192, seconds=300.0)

    blocks_executed = 0
    branches_executed = 0

    if task_limit:
        blocks = blocks[:task_limit]

    print(f"\n=======================================================")
    print(f"VERITAS End-to-End Feedback Study Executor")
    print(f"Study: {study_root.name}")
    print(f"Blocks: {len(blocks)} | Planned Branches per block: {len(ARMS)}")
    print(f"Actor Model: {actor_model_name}")
    print(f"Reference credit cap: {budget_credits} (reported, not hard-enforced)")
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
        all_done = all((block_id, b["arm"]) in existing_results for b in planned_branches)
        if all_done and resume:
            print(f"  -> All 5 branches already completed. Skipping block.")
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
            )
            parent_store.close()

            parent_patch = make_patch(parent_baseline, parent_workspace)
            write_text(block_dir / "parent.patch", parent_patch)

            # Private parent grading (hidden from all treatment arms)
            parent_grade = evaluate_task(task, parent_workspace, parent_baseline)
            parent_resolved = parent_grade["resolved"]
            parent_grade_data = {
                "parent_resolved": parent_resolved,
                "grader_status": parent_grade["status"],
                "grader_seconds": parent_grade["seconds"],
                "output": parent_grade["log"][:1000],
                "patch_hash": digest(parent_patch),
                "tree_hash": tree_hash(parent_workspace),
            }
            write_json(parent_grade_file, parent_grade_data)
            write_json(parent_session_file, {
                "step": parent_session.step,
                "history": parent_session.history,
            })
            print(f"  [Draft] Completed. Private parent grade: {'RESOLVED' if parent_resolved else 'INCORRECT'}")
        else:
            parent_grade_data = json.loads(parent_grade_file.read_text(encoding="utf-8"))
            parent_resolved = parent_grade_data["parent_resolved"]
            parent_session_data = json.loads(parent_session_file.read_text(encoding="utf-8"))
            parent_session = AgentSession(
                step=parent_session_data["step"],
                history=parent_session_data["history"],
            )
            parent_patch = (block_dir / "parent.patch").read_text(encoding="utf-8") if (block_dir / "parent.patch").exists() else ""
            print(f"  [Draft] Reused existing parent draft (parent_resolved={parent_resolved})")

        evidence_producer = make_evidence_producer(task, parent_baseline)

        # Execute the 5 treatment arms from the exact same parent state
        # Deterministically randomize execution order within each block to reduce
        # systematic time/order effects while preserving frozen assignments.
        for branch in sorted(
            planned_branches, key=lambda row: digest([block_id, "execution-order", row["arm"]])
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

            selector_spend = 0.0

            def record_branch_event(event):
                nonlocal selector_spend
                selector_spend += float(event.get("decision", {}).get("selector_credits", 0.0))
                branch_events.append(event)

            def selector_credit():
                # Selector computation charged ONLY to Arm E (adaptive)
                if arm == "adaptive":
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
                # This engineering pilot matches phase limits and records measured
                # spend; it does not claim a hard total-credit cap.
                remaining_credits_fn=lambda: None,
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
            )
            elapsed = time.monotonic() - arm_start
            branch_store.close()

            # Record selector credits consumed during run
            selector_overhead = selector_spend
            model_tokens = (rev_res.get("prompt_tokens") or 0) + (rev_res.get("known_completion_tokens") or 0)
            # Pilot accounting estimate; rates are fixed across arms and retained
            # in each row. The reference cap above is not an enforced stop rule.
            arm_total_credits = round(model_tokens * 0.002 + rev_res.get("tool_seconds", 0) * 0.05 + selector_overhead, 3)

            # Freeze final patch
            final_patch = make_patch(branch_baseline, branch_workspace)
            write_text(branch_dir / "final.patch", final_patch)

            # Independent final grading
            final_grade = evaluate_task(task, branch_workspace, branch_baseline)
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
                "patch_empty": patch_empty,
                "parent_resolved": parent_resolved,
                "grader_seconds": final_grade["seconds"],
                "total_credits": arm_total_credits,
                "credit_formula": "(prompt_tokens + completion_tokens) * 0.002 + tool_seconds * 0.05 + selector_credits",
                "credit_cap_enforced": False,
                "reference_credit_cap": budget_credits,
                "selector_credits": round(selector_overhead, 3),
                "actor_prompt_tokens": rev_res.get("prompt_tokens", 0),
                "actor_completion_tokens": rev_res.get("known_completion_tokens", 0),
                "actor_usage_complete": rev_res.get("usage_complete", False),
                "tool_seconds": round(rev_res.get("tool_seconds", 0), 3),
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
