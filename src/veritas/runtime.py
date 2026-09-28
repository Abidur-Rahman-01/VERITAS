import json
import math
import platform
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from scipy.special import expit

from .calibration import apply_artifact, load_artifact
from .context import compact_context
from .contracts import contract
from .controller import Controller, Risk
from .io import digest, write_json, write_jsonl
from .labels import grade_answer
from .models import ModelOutputError, proposal_from_text
from .provenance import critic_identity, implementation, verifier_identity
from .sanitize import redact, sanitize
from .schema import StepRecord, Usage, Verification
from .state import Checkpoint, tree_hash


@dataclass
class AgentSession:
    """Continuation state for the two awareness phases; never includes treatment A."""
    history: list = field(default_factory=list)
    step: int = 0


def run_phase(task, session, model, sandbox, store, output, *, trial_id, actor_name,
              phase, limits, protocol, cue="", boundary=None, on_step=None):
    """Baseline execution with equal phase caps; reuse contracts, sandbox and event writer.

    The legacy action-gate runner below keeps its existing policy semantics. This
    phase seam deliberately has no critic, controller, grader or review assignment.
    """
    from .awareness_store import StudyBudgetExceeded
    from .context import phase_context
    from .models import POLICY_COMPACT_SYSTEM, POLICY_SYSTEM

    if phase not in {"draft", "revision"} or (phase == "draft" and boundary is not None):
        raise ValueError("Invalid phase or premature boundary feedback")
    start = time.monotonic()
    tokens, steps, tool_seconds, status = 0, 0, 0.0, "step_limit"
    error = None
    request_ids, usage_complete = [], True
    system = POLICY_COMPACT_SYSTEM if protocol.compact else POLICY_SYSTEM
    for phase_step in range(limits.steps):
        remaining = limits.seconds - (time.monotonic() - start)
        if remaining <= 0 or tokens >= limits.completion_tokens:
            status = "time_limit" if remaining <= 0 else "token_limit"
            break
        context = phase_context(task, session.history, phase=phase, cue=cue, boundary=boundary,
            history_chars=protocol.history_chars, observation_chars=protocol.observation_chars,
            compact=protocol.compact, steps_remaining=limits.steps-phase_step,
            input_chars=protocol.input_chars)
        remaining = limits.seconds - (time.monotonic() - start)
        if remaining <= 0:
            status = "time_limit"
            break
        record = StepRecord(schema_version=2, trial_id=trial_id, attempt_id="attempt-001",
            phase=phase, event_id=digest([trial_id, session.step]), task_id=task.task_id,
            group_id=task.group_id, source=task.source, run_id=trial_id, model=actor_name,
            step_id=session.step, split=protocol.partition, context=redact(context), decision="skip",
            prompt_hash=digest({"system": system, "user": context}),
            prompt_redacted=redact(context) != context or redact(system) != system)
        session.step += 1
        steps += 1
        fatal = False
        try:
            raw, usage = model.complete(system, context,
                max_tokens=limits.completion_tokens-tokens, timeout_seconds=remaining)
            record.policy_usage = usage
            tokens += usage.completion_tokens
        except StudyBudgetExceeded:
            raise
        except ModelOutputError as exc:
            record.policy_usage = exc.usage
            tokens += exc.usage.completion_tokens
            raw = exc.raw
            record.blocked, record.decision, record.block_reason = True, "blocked", redact(str(exc))
        except Exception as exc:
            record.policy_usage = getattr(exc, "usage", Usage(measured=False))
            tokens += record.policy_usage.completion_tokens
            error = redact(f"{type(exc).__name__}: {exc}")
            record.blocked, record.decision, record.block_reason = True, "blocked", error
            raw, fatal, status = "", True, "model_error"
        record.actor_request_id = getattr(model, "last_call_id", None)
        if record.actor_request_id is not None:
            request_ids.append(record.actor_request_id)
        usage_complete = usage_complete and record.policy_usage.measured
        if not record.blocked:
            try:
                record.action = contract(proposal_from_text(raw))
            except (ValueError, TypeError, KeyError, SyntaxError) as exc:
                record.blocked, record.decision = True, "blocked"
                record.block_reason = redact(str(exc))[:1000]
                record.error_label, record.label_scope = 1, "operational"
                record.label_source = "deterministic_action_contract"
        if record.blocked:
            record.observation = sanitize(record.block_reason, "invalid_proposal", 1000)
        elif not record.policy_usage.measured:
            # Without measured completion usage the remaining phase budget is unknown.
            fatal, status, error = True, "unknown_usage", "Actor usage unavailable; phase stopped"
        elif time.monotonic() - start >= limits.seconds:
            status = "time_limit"
        else:
            record.state_before = tree_hash(sandbox.workspace)
            before_tool = time.monotonic()
            checkpoint = Checkpoint(sandbox.workspace, Path(output) / f"step-{record.step_id}-checkpoint")
            try:
                tool_remaining = limits.seconds - (time.monotonic() - start)
                if tool_remaining < 1:
                    status = "time_limit"
                elif hasattr(sandbox, "config"):
                    sandbox.config.timeout_seconds = max(1, min(
                        protocol.sandbox.timeout_seconds,
                        int(tool_remaining)))
                if status != "time_limit":
                    result = sandbox.execute(record.action)
                    record.executed = True
                    record.observation = sanitize(str(result.get("output", "")),
                        record.action.proposal.tool, protocol.observation_chars)
                    if result.get("exit_code") not in (0, None):
                        record.error_label, record.label_scope = 1, "operational"
                        record.label_source = "sandbox_nonzero_exit"
                        record.observation["exit_code"] = result["exit_code"]
                    record.state_after = tree_hash(sandbox.workspace)
                    if record.action.proposal.tool == "final_answer":
                        status = "submitted"
            except Exception as exc:
                record.restored_hash = checkpoint.restore()
                record.executed = False
                error = redact(f"{type(exc).__name__}: {exc}")
                record.observation = sanitize(error, "sandbox_error")
                fatal, status = True, "sandbox_error"
            finally:
                checkpoint.close()
                tool_seconds += time.monotonic() - before_tool
        store.append(record)
        session.history.append({"action": record.action.proposal.model_dump(mode="json")
                                if record.action else "invalid_proposal",
                                "observation": record.observation})
        if on_step is not None and record.executed:
            on_step(record, session)
        if fatal or status in {"submitted", "time_limit"}:
            break
        if record.blocked and not record.policy_usage.measured:
            status, error = "unknown_usage", "Malformed response with unknown usage"
            break
    return {"phase": phase, "termination": status, "steps": steps,
            "completion_tokens": tokens if usage_complete else None,
            "known_completion_tokens": tokens, "usage_complete": usage_complete,
            "actor_request_ids": request_ids, "seconds": time.monotonic()-start,
            "tool_seconds": tool_seconds, "error": error}


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
    graph_mode = config.run.policy == "graph"
    if graph_mode and (config.run.score_critic or config.run.audit_all or artifact):
        raise ValueError(
            "Graph policy requires score_critic=false, audit_all=false and no artifact"
        )
    trained_groups = getattr(critic, "metadata", {}).get("fit_groups", [])
    if config.run.score_critic and task.group_id in trained_groups:
        raise ValueError("Evaluation task appears in critic training fit groups")
    if not config.run.score_critic and (
        config.run.policy not in {"never", "always", "random", "risk", "graph"}
        or config.run.audit_all
        or artifact
    ):
        raise ValueError(
            "Disabling the critic requires a score-independent policy, no audit and no artifact"
        )
    if not artifact and not config.run.allow_uncalibrated and not graph_mode:
        raise ValueError(
            "Fitted artifact required. Use collection.yaml only for explicitly uncalibrated collection"
        )
    if artifact and task.group_id in artifact["fit_groups"] and assignment["split"] != "calib":
        raise ValueError("Evaluation task appears in calibration fit groups")
    controller = Controller(
        "never" if graph_mode else config.run.policy,
        config.run.verification_budget,
        config.run.threshold,
        config.run.dynamic_lambda,
        int(digest([config.seed, task.task_id])[:16], 16),
    )
    history, event_ids = [], []
    initial = (
        Checkpoint(sandbox.workspace, output / "initial-checkpoint")
        if config.run.recovery_mode == "restart"
        else None
    )
    critic_id = critic_identity(config, critic)
    verifier_id = verifier_identity(config)
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
    replans, graph_checks, graph_cache_hits, graph_model_calls = 0, 0, 0, 0
    graph_seconds = 0.0
    fallback_answer = None
    final_selection = "actor_answer"
    termination = "max_steps"
    start = time.monotonic()
    observer = None
    if config.opportunities.mode == "shadow":
        from .opportunities import WorkspaceObserver

        if task.kind != "swe":
            raise ValueError("Interface/caller opportunity observation requires a SWE task")
        import_root = sandbox.workspace / config.opportunities.import_root
        if not import_root.resolve().is_relative_to(sandbox.workspace.resolve()):
            raise ValueError("Opportunity import root escapes the workspace")
        observer = WorkspaceObserver(
            import_root, config.opportunities.target_identity,
            config.opportunities.caller_identity, config.opportunities.final_fallback,
        )
    for step in range(config.run.max_steps):
        if config.run.max_online_tokens is not None and (
            policy_tokens + critic_tokens + verifier_tokens >= config.run.max_online_tokens
        ):
            termination = "online_token_stop"
            break
        # Retain the task itself in full. Trim history, never the leading goal.
        if config.run.compact_history:
            context = compact_context(
                task,
                history,
                config.run.history_chars,
                config.run.observation_chars,
                config.run.max_steps - step,
            )
        else:
            while history and len(json.dumps(history)) > config.run.history_chars:
                history.pop(0)
            context = json.dumps(
                {"user_task": task.prompt, "recent_history": history}, ensure_ascii=False
            )
        proposal_error = None
        try:
            raw, usage = policy.propose(context)
        except ModelOutputError as e:
            raw, usage, proposal_error = e.raw, e.usage, str(e)
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
            if proposal_error:
                raise ValueError(proposal_error)
            action = contract(proposal_from_text(raw))
            if fallback_answer is not None and action.proposal.tool != "final_answer":
                raise ValueError("Final review permits only a revised final_answer")
        except (ValueError, SyntaxError, TypeError) as e:
            record.blocked, record.decision, record.block_reason = True, "blocked", str(e)
            record.error_label, record.label_scope = 1, "operational"
            record.label_source = "deterministic_action_contract"
            record.budget_spent = float(controller.budget.spent)
            store.append(record)
            event_ids.append(record.event_id)
            history.append(
                {
                    "action": "invalid_proposal",
                    "error": f"Invalid proposal: {str(e)[:300]}. Return ONLY a JSON object with 'tool' and 'args'.",
                }
            )
            replan_pending = True
            if config.run.max_replans is not None and replans >= config.run.max_replans:
                termination = "replan_limit"
                break
            replans += 1
            continue
        record.action = action
        if observer and action.proposal.tool == "final_answer":
            observer.observe(step, before_final=True)
        if config.run.score_critic:
            try:
                record.raw_logit, record.critic_usage = critic.score(context, action)
                if record.raw_logit is None or not math.isfinite(record.raw_logit):
                    raise ModelOutputError(
                        "Critic returned a nonfinite score", record.critic_usage, ""
                    )
            except Exception as e:
                record.raw_logit = None
                record.critic_error = redact(f"{type(e).__name__}: {e}")
                record.critic_usage = getattr(e, "usage", Usage(measured=False))
                record.critic_raw_output = redact(getattr(e, "raw", ""))[:2000]
        critic_tokens += record.critic_usage.total
        usage_complete &= record.critic_usage.measured
        record.impact = config.impact[action.action_class]
        if artifact and record.raw_logit is not None:
            if action.action_class not in artifact["statistics"]:
                record.fallback_reason = f"Missing calibrated class: {action.action_class}"
            else:
                calibrated = apply_artifact(record.model_dump(mode="json"), artifact)
                for key in ("p_error", "detection_rate", "false_positive_rate", "residual_loss"):
                    setattr(record, key, calibrated[key])
        elif record.raw_logit is not None:
            record.p_error = float(expit(record.raw_logit))
            # Explicit collection priors. They cannot be exported as an empirical artifact.
            record.detection_rate, record.false_positive_rate, record.residual_loss = 0.5, 0.1, 0.5
        risk = Risk(
            record.p_error if record.p_error is not None else 0.5,
            record.impact,
            record.detection_rate if record.detection_rate is not None else 0.5,
            record.false_positive_rate if record.false_positive_rate is not None else 0.1,
            record.residual_loss if record.residual_loss is not None else 0.5,
            record.verifier_cost,
            record.false_alarm_cost,
        )
        record.delta = risk.delta if record.p_error is not None else None
        if record.critic_error:
            record.fallback_reason = "Critic failed; no risk probability available"
        score_required = config.run.policy in {"confidence", "error_impact", "bavar_style", "rcvov"}
        if score_required and record.fallback_reason:
            # Explicit conservative fallback, charged to the SAME budget. Never invent risk.
            selected = controller.budget.can_afford(record.verifier_cost)
            if not selected:
                record.blocked, record.decision = True, "blocked"
                record.block_reason = record.fallback_reason + "; verification budget exhausted"
                record.budget_spent = float(controller.budget.spent)
                store.append(record)
                event_ids.append(record.event_id)
                # Nothing can resolve missing calibration within this task after budget exhaustion.
                break
        else:
            selected = controller.decide(risk)
        record.decision = "verify" if selected else "skip"
        # Verification happens before execution on an isolated clone. Only audit collection
        # needs a copied pre-state to measure restoration after a real action.
        checkpoint = (
            Checkpoint(sandbox.workspace, output / f"checkpoint-{step}")
            if config.run.audit_all
            else None
        )
        record.state_before = checkpoint.before if checkpoint else tree_hash(sandbox.workspace)
        rejected = False
        successful_edit = False
        stop_after_step = False
        try:
            if selected and not graph_mode:
                controller.reserve(risk)
            if graph_mode:
                record.verification, record.graph_trace = verifier.verify_graph(
                    context,
                    action,
                    risk.verifier_cost,
                    sandbox.workspace,
                    record.state_before,
                    controller.budget,
                    allow_review=(
                        step + 1 < config.run.max_steps
                        and (config.run.max_replans is None or replans < config.run.max_replans)
                        and (
                            config.run.max_online_tokens is None
                            or policy_tokens + critic_tokens + verifier_tokens
                            < config.run.max_online_tokens
                        )
                    ),
                )
                record.decision = "verify" if record.graph_trace["checks"] else "skip"
                graph_checks += len(record.graph_trace["checks"])
                graph_cache_hits += record.graph_trace["cache_hits"]
                graph_model_calls += record.graph_trace["semantic_calls"]
                graph_seconds += record.graph_trace["seconds"]
                verifier_tokens += record.verification.usage.total
                usage_complete &= record.verification.usage.measured
                rejected = record.verification.verdict == "FAIL"
                can_replan = config.run.max_replans is None or replans < config.run.max_replans
                if record.verification.verdict == "REVIEW" and can_replan:
                    # An opinion permits a single final-only revision; never a proven rejection.
                    record.revision_requested = True
                    fallback_answer = action.proposal.args["answer"]
                    rejected = True
                if record.verification.verdict == "ERROR":
                    record.fallback_reason = (
                        "Graph evidence unavailable; execute under action contract"
                    )
            elif selected or config.run.audit_all:
                record.audit_only = not selected
                try:
                    record.verification = verifier.verify(
                        context, action, risk.verifier_cost, sandbox.workspace
                    )
                except Exception as e:
                    record.verification = Verification(
                        verdict="ERROR",
                        reason=f"{type(e).__name__}: {e}",
                        cost=risk.verifier_cost,
                        usage=getattr(e, "usage", Usage(measured=False)),
                    )
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
                if checkpoint:
                    record.restored_hash = checkpoint.restore()
                record.recovery_seconds = time.monotonic() - before_restore
                feedback = record.verification.reason
                if graph_mode:
                    feedback = feedback[:400]
                    if record.revision_requested:
                        feedback = (
                            "Advisory review (not proof): "
                            + feedback
                            + " Return final_answer only; retain your answer if the critique is wrong."
                        )
                record.observation = sanitize(feedback, "verifier")
                if initial:
                    initial.restore()
                    history.clear()
                replan_pending = True
                if config.run.max_replans is not None and replans >= config.run.max_replans:
                    termination, stop_after_step = "replan_limit", True
                else:
                    replans += 1
            else:
                result = sandbox.execute(action)
                record.executed = True
                successful_edit = (
                    action.mutation_type != "none" and isinstance(result, dict)
                    and result.get("exit_code") == 0
                )
                obs_content = result.get("output", "") if isinstance(result, dict) else str(result)
                if isinstance(result, dict) and result.get("exit_code") not in (0, None):
                    obs_content = (
                        f"Command failed (exit code {result['exit_code']}):\n{obs_content}"
                    )
                record.observation = sanitize(
                    obs_content, action.proposal.tool, config.sandbox.max_output_chars
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
            if observer and action.proposal.tool != "final_answer":
                observer.observe(step, successful_edit=successful_edit)
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
                termination = "final_answer"
                break
            if stop_after_step:
                break
        finally:
            if checkpoint:
                checkpoint.close()
    if final is None and fallback_answer is not None:
        final, final_success = fallback_answer, grade_answer(task, fallback_answer)
        final_selection = "reviewed_original_fallback"
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
        "critic_enabled": config.run.score_critic,
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
        "termination_reason": termination,
        "final_selection": final_selection,
        "replans": replans,
        "graph_checks": graph_checks,
        "graph_cache_hits": graph_cache_hits,
        "graph_model_calls": graph_model_calls,
        "graph_seconds": graph_seconds,
        "python": platform.python_version(),
    }
    write_json(output / "summary.json", summary)
    if observer:
        opportunities = observer.finish(termination)
        write_json(output / "opportunities.json", opportunities)
        summary["opportunity_observation"] = opportunities
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
    selected_tasks=None,
):
    from .critic import TrainedCritic
    from .data import load_tasks
    from .graph_verifier import GraphVerifier
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
    artifact = load_artifact(artifact) if artifact else None
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
            "implementation": implementation([p.name for p in Path(__file__).parent.glob("*.py")]),
            "tasks_manifest": digest(json.loads((Path(tasks_dir) / "manifest.json").read_text())),
        },
    )
    policy = LocalModel(config.model)
    critic = TrainedCritic(critic_dir) if critic_dir else LocalModel(config.critic)
    verifier_model = LocalModel(config.verifier)
    store = EventStore(output / "events.sqlite")
    summaries, predictions = [], []
    try:
        task_pairs = (
            selected_tasks
            if selected_tasks is not None
            else load_tasks(tasks_dir, split, source, limit)
        )
        for task, assignment in task_pairs:
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
            verifier = (
                GraphVerifier(verifier_model, sandbox_config, config.probes, config.graph)
                if config.run.policy == "graph"
                else Verifier(verifier_model, sandbox_config, config.probes)
            )
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
                        "model_name_or_path": config.model.name.replace(":", "__"),
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
