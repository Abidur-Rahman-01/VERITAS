import json
import platform
import shutil
import time
import uuid
from pathlib import Path

from scipy.special import expit

from .calibration import apply_artifact
from .contracts import contract
from .controller import Controller, Risk
from .io import digest, write_json, write_jsonl
from .labels import grade_answer
from .models import proposal_from_text
from .sanitize import redact, sanitize
from .schema import StepRecord, Verification
from .state import Checkpoint, tree_hash


def build_context(task, history, limit):
    return json.dumps({"user_task": task.prompt, "recent_history": history}, ensure_ascii=False)[
        -limit:
    ]


def run_task(
    task,
    assignment,
    config,
    policy,
    critic,
    verifier,
    sandbox,
    store,
    output,
    artifact=None,
    run_id=None,
):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    run_id = run_id or uuid.uuid4().hex
    if not artifact and not config.run.allow_uncalibrated:
        raise ValueError(
            "Fitted artifact required. Use collection.yaml only for explicitly uncalibrated collection"
        )
    if artifact and task.group_id in artifact["fit_groups"] and assignment["split"] != "calib":
        raise ValueError("Evaluation task appears in calibration fit groups")
    controller = Controller(
        config.run.policy,
        config.run.verification_budget,
        config.run.threshold,
        config.run.dynamic_lambda,
        config.seed,
    )
    history, event_ids = [], []
    initial = (
        Checkpoint(sandbox.workspace, output / "initial-checkpoint")
        if config.run.recovery_mode == "restart"
        else None
    )
    critic_id = (
        digest(critic.metadata)
        if hasattr(critic, "metadata")
        else digest(config.critic.model_dump())
    )
    verifier_id = digest([config.verifier.model_dump(), config.probes])
    if artifact and (
        artifact.get("critic_id") != critic_id or artifact.get("verifier_id") != verifier_id
    ):
        raise ValueError(
            "Critic/verifier configuration differs from calibration; recollect or recalibrate"
        )
    final, final_success = None, None
    policy_tokens, critic_tokens, verifier_tokens, audit_tokens = 0, 0, 0, 0
    usage_complete = True
    replan_tokens, recovery_seconds = 0, 0.0
    replan_pending = False
    start = time.monotonic()
    for step in range(config.run.max_steps):
        # Retain the task itself in full. Trim history, never the leading goal.
        while history and len(json.dumps(history)) > config.run.history_chars:
            history.pop(0)
        context = json.dumps(
            {"user_task": task.prompt, "recent_history": history}, ensure_ascii=False
        )
        raw, usage = policy.propose(context)
        policy_tokens += usage.total
        usage_complete &= usage.measured
        if replan_pending:
            replan_tokens += usage.total
        replan_pending = False
        record = StepRecord(
            event_id=digest([run_id, task.task_id, step]),
            task_id=task.task_id,
            group_id=task.group_id,
            source=task.source,
            run_id=run_id,
            model=config.model.name,
            critic_id=critic_id,
            verifier_id=verifier_id,
            step_id=step,
            context=redact(context),
            split=assignment["split"],
            calibration_role=assignment.get("calibration_role"),
            decision="skip",
            policy_usage=usage,
            verifier_cost=config.run.verification_cost,
            false_alarm_cost=config.run.false_alarm_cost,
        )
        try:
            action = contract(proposal_from_text(raw))
        except (ValueError, SyntaxError, TypeError) as e:
            record.blocked, record.decision, record.block_reason = True, "blocked", str(e)
            record.error_label, record.label_scope = 1, "operational"
            record.label_source = "deterministic_action_contract"
            record.budget_spent = float(controller.budget.spent)
            store.append(record)
            event_ids.append(record.event_id)
            history.append({"blocked_proposal": redact(raw)[:8000], "diagnostic": str(e)[:2000]})
            replan_pending = True
            continue
        record.action = action
        record.raw_logit, record.critic_usage = critic.score(context, action)
        critic_tokens += record.critic_usage.total
        usage_complete &= record.critic_usage.measured
        record.impact = config.impact[action.action_class]
        if artifact:
            calibrated = apply_artifact(record.model_dump(mode="json"), artifact)
            for key in ("p_error", "detection_rate", "false_positive_rate", "residual_loss"):
                setattr(record, key, calibrated[key])
        else:
            record.p_error = float(expit(record.raw_logit))
            # Explicit collection priors. They cannot be exported as an empirical artifact.
            record.detection_rate, record.false_positive_rate, record.residual_loss = 0.5, 0.1, 0.5
        risk = Risk(
            record.p_error,
            record.impact,
            record.detection_rate,
            record.false_positive_rate,
            record.residual_loss,
            record.verifier_cost,
            record.false_alarm_cost,
        )
        record.delta = risk.delta
        selected = controller.decide(risk)
        record.decision = "verify" if selected else "skip"
        checkpoint = Checkpoint(sandbox.workspace, output / f"checkpoint-{step}")
        record.state_before = checkpoint.before
        rejected = False
        try:
            if selected:
                controller.reserve(risk)
            if selected or config.run.audit_all:
                record.audit_only = not selected
                try:
                    record.verification = verifier.verify(
                        context, action, risk.verifier_cost, sandbox.workspace
                    )
                except Exception as e:
                    record.verification = Verification(
                        verdict="ERROR", reason=f"{type(e).__name__}: {e}", cost=risk.verifier_cost
                    )
                    record.verification.usage.measured = False
                record.verification.reason = redact(record.verification.reason)
                if record.audit_only:
                    audit_tokens += record.verification.usage.total
                else:
                    verifier_tokens += record.verification.usage.total
                usage_complete &= record.verification.usage.measured
                rejected = selected and record.verification.verdict != "PASS"
            if action.proposal.tool == "final_answer":
                success = grade_answer(task, action.proposal.args["answer"])
                if success is not None and (task.kind == "gsm8k" or success):
                    # Evaluation label is never supplied back to the policy or verifier.
                    record.error_label, record.label_scope = int(not success), "semantic"
                    record.label_source = (
                        "official_numeric_answer"
                        if task.kind == "gsm8k"
                        else "official_exact_string_answer"
                    )
            if rejected:
                before_restore = time.monotonic()
                record.restored_hash = checkpoint.restore()
                record.recovery_seconds = time.monotonic() - before_restore
                record.observation = sanitize(record.verification.reason, "verifier")
                if initial:
                    initial.restore()
                    history.clear()
                replan_pending = True
            else:
                result = sandbox.execute(action)
                record.executed = True
                record.observation = sanitize(
                    json.dumps(result), action.proposal.tool, config.sandbox.max_output_chars
                )
                # Nonzero exit only establishes operational failure. A failed test command may be
                # an excellent diagnostic action; never call that a semantic error automatically.
                if action.proposal.tool != "final_answer" and result["exit_code"] != 0:
                    record.error_label, record.label_scope = 1, "operational"
                    record.label_source = "sandbox_nonzero_exit"
                if config.run.audit_all:
                    post = Checkpoint(sandbox.workspace, output / f"post-state-{step}")
                    try:
                        before_restore = time.monotonic()
                        record.restored_hash = checkpoint.restore()
                        record.recovery_seconds = time.monotonic() - before_restore
                        post.restore()  # Continue the same baseline trajectory after measuring restore.
                    finally:
                        post.close()
                if action.proposal.tool == "final_answer":
                    final, final_success = (
                        action.proposal.args["answer"],
                        grade_answer(task, action.proposal.args["answer"]),
                    )
            record.state_after = tree_hash(sandbox.workspace)
            record.budget_spent = float(controller.budget.spent)
            recovery_seconds += record.recovery_seconds
            store.append(record)
            event_ids.append(record.event_id)
            history.append(
                {
                    "action": action.proposal.model_dump(mode="json"),
                    "observation": record.observation,
                }
            )
            if final is not None:
                break
        finally:
            checkpoint.close()
    if final is None and task.kind in {"gsm8k", "math"}:
        final_success = False
    summary = {
        "task_id": task.task_id,
        "group_id": task.group_id,
        "source": task.source,
        "run_id": run_id,
        "split": assignment["split"],
        "policy": config.run.policy,
        "model": config.model.name,
        "calibrated": bool(artifact),
        "final_answer": final,
        "seed": config.seed,
        "recovery_mode": config.run.recovery_mode,
        "task_success": final_success,
        "steps": len(event_ids),
        "event_ids": event_ids,
        "policy_tokens": policy_tokens,
        "critic_tokens": critic_tokens,
        "verifier_tokens": verifier_tokens,
        "audit_tokens": audit_tokens,
        "total_online_tokens": policy_tokens + critic_tokens + verifier_tokens,
        "replan_tokens": replan_tokens,
        "token_usage_complete": usage_complete,
        "recovery_seconds": recovery_seconds,
        "verification_spent": float(controller.budget.spent),
        "verification_budget": float(controller.budget.total),
        "budget_violation": False,
        "seconds": time.monotonic() - start,
        "python": platform.python_version(),
    }
    write_json(output / "summary.json", summary)
    if initial:
        initial.close()
    return summary


def collect(
    tasks_dir,
    config,
    output,
    split=None,
    source=None,
    limit=None,
    artifact=None,
    critic_dir=None,
    images=None,
):
    from .critic import TrainedCritic
    from .data import load_tasks
    from .models import LocalModel
    from .sandbox import DockerSandbox, initialize_swe_workspace, make_patch
    from .store import EventStore
    from .verifier import Verifier

    output = Path(output)
    if (output / "run.json").exists():
        raise ValueError(
            "Run directory already exists. Use a new run ID; records are never overwritten"
        )
    output.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    artifact = json.loads(Path(artifact).read_text()) if artifact else None
    image_map = json.loads(Path(images).read_text()) if images else {}
    write_json(
        output / "run.json",
        {
            "run_id": run_id,
            "config": config.model_dump(mode="json"),
            "split": split,
            "source": source,
            "limit": limit,
            "artifact": artifact,
            "critic_dir": str(critic_dir) if critic_dir else None,
            "tasks_manifest": digest(json.loads((Path(tasks_dir) / "manifest.json").read_text())),
        },
    )
    policy = LocalModel(config.model)
    critic = TrainedCritic(critic_dir) if critic_dir else LocalModel(config.critic)
    verifier_model = LocalModel(config.verifier)
    store = EventStore(output / "events.sqlite")
    summaries, predictions = [], []
    try:
        for task, assignment in load_tasks(tasks_dir, split, source, limit):
            task_output = output / digest(task.task_id)[:20]
            workspace = task_output / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            sandbox_config = config.sandbox.model_copy(deep=True)
            if task.kind == "swe":
                image = image_map.get(task.private["instance_id"])
                if not image:
                    raise ValueError(
                        f"No prepared image for {task.private['instance_id']}; run swe image-map first"
                    )
                sandbox_config.image = image
            sandbox = DockerSandbox(workspace, sandbox_config)
            image_digest = sandbox.preflight()
            if task.kind == "swe":
                initialize_swe_workspace(
                    sandbox_config.image, workspace, task.base_commit, sandbox_config.platform
                )
                shutil.copytree(workspace, task_output / "baseline")
            verifier = Verifier(verifier_model, sandbox_config, config.probes)
            summary = run_task(
                task,
                assignment,
                config,
                policy,
                critic,
                verifier,
                sandbox,
                store,
                task_output,
                artifact,
                run_id,
            )
            summary["image_digest"] = image_digest
            write_json(task_output / "summary.json", summary)
            if task.kind == "swe":
                patch = make_patch(task_output / "baseline", workspace)
                (task_output / "prediction.patch").write_text(patch)
                predictions.append(
                    {
                        "instance_id": task.private["instance_id"],
                        "model_patch": patch,
                        "model_name_or_path": config.model.name,
                    }
                )
            summaries.append(summary)
            write_jsonl(output / "summaries.jsonl", summaries)
            write_jsonl(output / "predictions.jsonl", predictions)
            print(
                f"{task.task_id}: {summary['steps']} steps, success={summary['task_success']}",
                flush=True,
            )
    except Exception as e:
        write_json(
            output / "failure.json",
            {
                "error": type(e).__name__,
                "message": redact(str(e)),
                "completed_tasks": len(summaries),
                "run_id": run_id,
                "note": "Run incomplete; missing API usage is not counted as zero measured cost",
            },
        )
        raise
    finally:
        policy.close()
        critic.close()
        verifier_model.close()
        store.close()
    if not summaries:
        raise ValueError("No tasks matched source/split filters")
    return {"run_id": run_id, "tasks": len(summaries), "output": str(output)}
