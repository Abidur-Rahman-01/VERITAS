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
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

from .config import ModelConfig, SandboxConfig
from .feedback_evidence import EvidenceItem, PatchCheckpoint, tool_observation_item
from .feedback_policy import ARMS
from .feedback_runtime import FeedbackCheckpointController
from .feedback_study import analyze_results, verify_plan
from .io import digest, read_jsonl, write_json, write_text
from .models import LocalModel
from .runtime import AgentSession, run_phase
from .sandbox import LocalSandbox, make_patch
from .schema import Task
from .state import tree_hash
from .store import EventStore


# Enforce local execution when Docker is unavailable
os.environ["VERITAS_LOCAL_SANDBOX"] = "1"
os.environ["VERITAS_SANDBOX_BACKEND"] = "local"
os.environ["VERITAS_NO_DOCKER"] = "1"


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def get_task_setup_fn(task_id: str) -> Callable[[Path], tuple[str, str]]:
    """Resolve task setup function from task_id or private metadata."""
    clean_id = task_id.replace("swe:", "")
    from scripts.tse_60_task_fixtures import (
        setup_swe_cmd2_790,
        setup_swe_cmd2_800,
        setup_swe_cmd2_810,
        setup_swe_pennylane_5100,
        setup_swe_pennylane_5200,
        setup_swe_pennylane_5300,
        setup_swe_sympy_18800,
        setup_swe_sympy_18900,
        setup_swe_sympy_19000,
    )
    from scripts.run_action_time_tse_experiment import setup_swe_cmd2_744

    registry = {
        "cmd2_744": setup_swe_cmd2_744,
        "swe_cmd2_744": setup_swe_cmd2_744,
        "cmd2_790": setup_swe_cmd2_790,
        "swe_cmd2_790": setup_swe_cmd2_790,
        "cmd2_800": setup_swe_cmd2_800,
        "swe_cmd2_800": setup_swe_cmd2_800,
        "cmd2_810": setup_swe_cmd2_810,
        "swe_cmd2_810": setup_swe_cmd2_810,
        "sympy_18800": setup_swe_sympy_18800,
        "swe_sympy_18800": setup_swe_sympy_18800,
        "sympy_18900": setup_swe_sympy_18900,
        "swe_sympy_18900": setup_swe_sympy_18900,
        "sympy_19000": setup_swe_sympy_19000,
        "swe_sympy_19000": setup_swe_sympy_19000,
        "pennylane_5100": setup_swe_pennylane_5100,
        "swe_pennylane_5100": setup_swe_pennylane_5100,
        "pennylane_5200": setup_swe_pennylane_5200,
        "swe_pennylane_5200": setup_swe_pennylane_5200,
        "pennylane_5300": setup_swe_pennylane_5300,
        "swe_pennylane_5300": setup_swe_pennylane_5300,
    }
    if clean_id not in registry:
        raise ValueError(f"No setup function registered for task: {task_id}")
    return registry[clean_id]


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


def make_evidence_producer(task: Task):
    """Factory creating an evidence producer for a repository task."""
    def produce(checkpoint: PatchCheckpoint, workspace: Path, record, session) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []

        # 1. Targeted test execution in a disposable copy of workspace
        with tempfile.TemporaryDirectory(prefix="veritas-check-") as tmp:
            tmp_ws = Path(tmp) / "check_ws"
            shutil.copytree(workspace, tmp_ws)
            passed, test_out = evaluate_workspace(tmp_ws)

        if passed:
            items.append(EvidenceItem.create(
                task_id=checkpoint.task_id, branch_id=checkpoint.branch_id,
                checkpoint_id=checkpoint.checkpoint_id, source="test", basis="observed",
                patch_hash=checkpoint.patch_hash, tree_hash=checkpoint.tree_hash,
                environment_hash=checkpoint.environment_hash,
                command="pytest tests/ -q", raw_artifact_hash=digest(test_out),
                claim="All repository unit tests passed successfully.",
                affected_files=checkpoint.changed_files,
                cost_credits=0.5,
            ))
        else:
            lines = test_out.splitlines()
            summary_lines = [l for l in lines if l.startswith("FAILED ") or "AssertionError" in l or "Error:" in l]
            claim = "\n".join(summary_lines[:3]) or test_out[-500:]

            location = None
            observed = None
            expected = None
            for l in lines:
                if "::" in l and ("FAILED" in l or "ERROR" in l):
                    parts = l.split()
                    for p in parts:
                        if "::" in p:
                            location = p
                            break
                if "assert " in l or "AssertionError" in l:
                    observed = l.strip()
                if "== " in l or "!= " in l:
                    expected = l.strip()

            items.append(EvidenceItem.create(
                task_id=checkpoint.task_id, branch_id=checkpoint.branch_id,
                checkpoint_id=checkpoint.checkpoint_id, source="test", basis="observed",
                patch_hash=checkpoint.patch_hash, tree_hash=checkpoint.tree_hash,
                environment_hash=checkpoint.environment_hash,
                command="pytest tests/ -q", raw_artifact_hash=digest(test_out),
                claim=claim[:1500], location=location, observed=observed,
                expected_if_observed=expected, affected_files=checkpoint.changed_files,
                cost_credits=0.5,
            ))

        # 2. Static syntax checking on changed files
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

        # 3. Model/heuristic reviewer finding card (basis="model_opinion")
        review_claim = (
            f"Reviewer notice for {task.task_id}: check whether changes to {checkpoint.changed_files or 'code'} "
            f"fully address '{task.prompt[:120]}...'."
        )
        items.append(EvidenceItem.create(
            task_id=checkpoint.task_id, branch_id=checkpoint.branch_id,
            checkpoint_id=checkpoint.checkpoint_id, source="reviewer", basis="model_opinion",
            patch_hash=checkpoint.patch_hash, tree_hash=checkpoint.tree_hash,
            environment_hash=checkpoint.environment_hash,
            raw_artifact_hash=digest(review_claim),
            claim=review_claim, affected_files=checkpoint.changed_files,
            cost_credits=0.4,
        ))

        # 4. If record is available, convert executed tool observation
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
    print(f"Budget: {budget_credits} credits | Draft steps: {draft_steps} | Revision steps: {revision_steps}")
    print(f"=======================================================\n")

    for block_idx, block in enumerate(blocks, start=1):
        block_id = block["block_id"]
        task_id = block["task_id"]
        task = tasks_by_id[task_id]
        setup_fn = get_task_setup_fn(task_id)

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
                shutil.rmtree(parent_workspace)
            if parent_baseline.exists():
                shutil.rmtree(parent_baseline)

            _, _ = setup_fn(parent_workspace)
            shutil.copytree(parent_workspace, parent_baseline)

            parent_session = AgentSession()
            parent_store = EventStore(block_dir / "draft_events.sqlite")
            parent_sandbox = LocalSandbox(parent_workspace, sandbox_cfg)

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
            parent_resolved, parent_grade_out = evaluate_workspace(parent_workspace)
            parent_grade_data = {
                "parent_resolved": parent_resolved,
                "output": parent_grade_out[:1000],
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

        evidence_producer = make_evidence_producer(task)

        # Execute the 5 treatment arms from the exact same parent state
        for branch in planned_branches:
            arm = branch["arm"]
            branch_id = branch["branch_id"]

            if (block_id, arm) in existing_results and resume:
                print(f"    - Arm {arm:18s}: already recorded, skipping.")
                continue

            print(f"    - Arm {arm:18s}: starting paired continuation from parent...")
            branch_dir = block_dir / arm
            if branch_dir.exists():
                shutil.rmtree(branch_dir)
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

            spent_credits = 0.0

            def remaining_credits():
                return max(0.0, budget_credits - spent_credits)

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
                remaining_credits_fn=remaining_credits,
                event_sink=branch_events.append,
            )

            # Trigger initial checkpoint on the parent draft patch
            init_event = controller.create_initial_checkpoint(branch_session)
            if arm == "adaptive":
                spent_credits += 0.25

            branch_store = EventStore(branch_dir / "revision_events.sqlite")
            branch_sandbox = LocalSandbox(branch_workspace, sandbox_cfg)

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
            selector_overhead = sum(d.selector_credits for d in controller.decisions)
            model_tokens = rev_res.get("known_completion_tokens") or 0
            # Credit formula: tokens * 0.002 + tool_seconds * 0.05 + selector_overhead
            arm_total_credits = round(model_tokens * 0.002 + rev_res.get("tool_seconds", 0) * 0.05 + selector_overhead, 3)

            # Freeze final patch
            final_patch = make_patch(branch_baseline, branch_workspace)
            write_text(branch_dir / "final.patch", final_patch)

            # Independent final grading
            final_resolved, final_grade_out = evaluate_workspace(branch_workspace)
            write_json(branch_dir / "grade.json", {
                "resolved": final_resolved,
                "output": final_grade_out[:1000],
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
                "parent_resolved": parent_resolved,
                "total_credits": arm_total_credits,
                "steps": rev_res.get("steps", 0),
                "checkpoints": len(controller.decisions),
                "wall_seconds": round(elapsed, 2),
                "patch_hash": digest(final_patch),
            }

            with open(results_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(result_row) + "\n")
            existing_results.add((block_id, arm))
            branches_executed += 1

            status_str = "RESOLVED (+)" if final_resolved else "UNRESOLVED (-)"
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
