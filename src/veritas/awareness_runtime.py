"""Sequential execution, deferred audit and source-compatible independent SWE grading."""

import ast
import json
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from .awareness import Assignment, DisclosurePolicy, read_study
from .awareness_grading import GradeRecord, grade_patch, parse_grade  # noqa: F401
from .awareness_store import (
    ACTIVE_STATES,
    MeteredModel,
    StudyBudgetExceeded,
    StudyStore,
    TrialOutcome,
    coordinator_lock,
)
from .io import digest, file_hash, write_json, write_text
from .models import LocalModel
from .patch_review import boundary_message, make_packet, review_patch
from .runtime import AgentSession, run_phase
from .sandbox import DockerSandbox, initialize_swe_workspace, make_patch
from .sanitize import redact
from .state import tree_hash
from .store import EventStore


@dataclass
class Services:
    """Injectable IO for tests; the CLI always uses real models, Docker and SWE."""
    model_factory: object = LocalModel
    sandbox_factory: object = DockerSandbox
    initialize: object = initialize_swe_workspace
    patch: object = make_patch


def trial_directory(root, trial_id):
    return Path(root) / "trials" / trial_id / "attempt-001"


def _test_functions(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 1000000:
        return {}
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, UnicodeError):
        return {}
    return {node.name: ast.dump(node, include_attributes=False) for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and
            node.name.startswith("test_")}


def behavioral_metrics(patch, history, baseline=None, workspace=None):
    lines = patch.splitlines()
    paths = sorted({line[6:] for line in lines if line.startswith("+++ b/") or
                    line.startswith("--- a/")})
    tests_added, tests_modified = None, None
    if baseline is not None and workspace is not None:
        tests_added, tests_modified = 0, 0
        for path in paths:
            if not path.endswith(".py") or not (Path(path).name.startswith("test_") or
                                                 "tests" in Path(path).parts):
                continue
            if Path(path).is_absolute() or ".." in Path(path).parts:
                continue
            before, after = _test_functions(Path(baseline) / path), _test_functions(Path(workspace) / path)
            tests_added += len(after.keys()-before.keys())
            tests_modified += sum(after[k] != before[k] for k in before.keys() & after.keys())
    tests_run, language = 0, []
    for item in history:
        action = item.get("action")
        if not isinstance(action, dict):
            continue
        tests_run += int(action.get("tool") == "run_tests")
        if action.get("tool") == "final_answer":
            language.append(action["args"].get("answer", ""))
    prose = re.sub(r"```.*?```|`[^`]*`|(?m:^>.*$)", "", "\n".join(language), flags=re.S)
    words = re.findall(r"\b[a-z]+\b", prose.lower())
    hedges = sum(w in {"perhaps", "maybe", "possibly", "likely", "uncertain", "probably"}
                 for w in words)
    return {"extractor_version": 2, "extractor_hash": file_hash(Path(__file__)),
            "patch_hash": digest(patch), "history_hash": digest(history),
            "added_lines": sum(line.startswith("+") and not line.startswith("+++") for line in lines),
            "deleted_lines": sum(line.startswith("-") and not line.startswith("---") for line in lines),
            "files_changed": len(paths), "test_functions_added": tests_added,
            "test_functions_modified": tests_modified, "test_commands": tests_run,
            "hedge_words": hedges, "eligible_words": len(words),
            "hedging_rate": hedges / len(words) if words else None,
            "defensive_test_count": None, "self_reported_confidence": None,
            "limitations": "Python AST counts; intent unclassified. Language is final-answer prose only."}


def run_trial(root, spec, task, job, db, services=None):
    services = services or Services()
    start = time.monotonic()
    directory = trial_directory(root, job.trial_id)
    directory.mkdir(parents=True, exist_ok=False)
    work, baseline = directory / "workspace", directory / "baseline"
    models = []
    event_store = None
    outcome = TrialOutcome(trial_id=job.trial_id, runtime_status="failed")
    session = AgentSession()
    last_snapshot = None

    def save_snapshot(record=None, current=None):
        nonlocal last_snapshot
        patch = services.patch(baseline, work)
        step = 0 if record is None else record.step_id + 1
        path = directory / "snapshots" / f"{step:08d}.patch"
        write_text(path, patch)
        db.freeze_file(path)
        snapshot = {"path": path.relative_to(Path(root)).as_posix(),
                    "patch_hash": digest(patch), "tree_hash": tree_hash(work),
                    "step": step, "phase": record.phase if record else "prepare"}
        session_path = path.with_suffix(".session.json")
        write_json(session_path, {"step": session.step, "history": session.history,
                                 "tree_hash": snapshot["tree_hash"]})
        db.freeze_file(session_path)
        db.put_artifact(f"snapshot/{job.trial_id}/{step:08d}", snapshot)
        last_snapshot = snapshot

    def freeze_patch(name, patch, tree):
        path = directory / f"{name}.patch"
        write_text(path, patch)
        db.freeze_file(path)
        db.put_artifact(f"{name}/{job.trial_id}", {
            "path": path.relative_to(Path(root)).as_posix(),
            "patch_hash": digest(patch), "tree_hash": tree})

    try:
        sandbox_config = spec.sandbox.model_copy(deep=True)
        instance = task.private["instance_id"]
        sandbox_config.image = spec.images[instance]
        sandbox = services.sandbox_factory(work, sandbox_config)
        outcome.image_digest = sandbox.preflight()
        expected = spec.image_digests.get(instance)
        if expected and outcome.image_digest != expected:
            raise ValueError("Prepared image digest differs from frozen protocol")
        services.initialize(sandbox_config.image, work, task.base_commit, sandbox_config.platform)
        shutil.copytree(work, baseline)
        base_hash = tree_hash(work)
        if spec.base_tree_hashes.get(instance) not in (None, base_hash):
            raise ValueError("Base workspace differs from frozen tree hash")
        base_key = f"base/{job.task_id}"
        base_identity = {"tree_hash": base_hash, "image_digest": outcome.image_digest,
                         "base_commit": task.base_commit}
        if db.artifact(base_key) is None:
            db.put_artifact(base_key, base_identity)
        elif db.artifact(base_key) != base_identity:
            raise ValueError("Task arms did not start from the same base workspace/image")
        write_json(directory / "base.json", {"tree_hash": base_hash,
                   "image_digest": outcome.image_digest, "base_commit": task.base_commit})
        db.freeze_file(directory / "base.json")
        save_snapshot()
        actor = next(a for a in spec.actors if a.id == job.actor_id)
        actor_model = services.model_factory(actor.model)
        models.append(actor_model)
        cue = DisclosurePolicy(probability=job.disclosed_probability).render() \
            if job.disclosure_assigned else ""
        event_store = EventStore(directory / "events.sqlite")
        args = dict(task=task, session=session, sandbox=sandbox, store=event_store, output=directory,
                    trial_id=job.trial_id, actor_name=actor.id, protocol=spec, cue=cue,
                    on_step=save_snapshot)
        draft = run_phase(model=MeteredModel(actor_model, db, spec, job.trial_id, "actor_draft",
                          actor.model_dump(mode="json")), phase="draft", limits=spec.draft, **args)
        outcome.phase_results["draft"] = draft
        patch = services.patch(baseline, work)
        outcome.draft_patch_hash = digest(patch)
        outcome.draft_tree_hash = tree_hash(work)
        freeze_patch("draft", patch, outcome.draft_tree_hash)
        write_json(directory / "draft-session.json", {"history": session.history, "step": session.step,
                   "tree_hash": outcome.draft_tree_hash})
        db.freeze_file(directory / "draft-session.json")
        draft_workspace = directory / "draft-workspace"
        shutil.copytree(work, draft_workspace)
        outcome.metrics["draft"] = behavioral_metrics(patch, session.history, baseline, work)
        packet = make_packet(task, patch, work, session.history, spec.review)
        write_json(directory / "packet.json", packet)
        db.freeze_file(directory / "packet.json")
        db.put_artifact(f"packet/{job.trial_id}", {"packet": packet, "patch_hash": digest(patch)})
        db.transition(job.trial_id, "draft_frozen", {"patch_hash": outcome.draft_patch_hash,
                                                   "packet_hash": digest(packet)})
        if draft["error"]:
            raise RuntimeError(draft["error"])
        review = None
        if job.actual_assignment:
            from .patch_review import ReviewRecord

            try:
                reviewer_model = services.model_factory(spec.reviewer.model)
                models.append(reviewer_model)
                review = review_patch(packet, outcome.draft_patch_hash,
                    MeteredModel(reviewer_model, db, spec, job.trial_id, "online_review",
                                 spec.reviewer.model_dump(mode="json")), spec.review)
            except StudyBudgetExceeded:
                raise
            except Exception as exc:
                # Reviewer initialization is also an unavailable review, never a lost
                # revision opportunity or an implicit change of assigned A.
                review = ReviewRecord(verdict="ERROR", packet_hash=digest(packet),
                    draft_patch_hash=outcome.draft_patch_hash, error=redact(str(exc)),
                    reviewer_identity=spec.reviewer.model_dump(mode="json"))
        boundary = {"message": boundary_message(review),
                    "review": review.model_dump(mode="json") if review else None}
        boundary["message_hash"] = digest(boundary["message"])
        write_json(directory / "review.json", boundary)
        db.freeze_file(directory / "review.json")
        db.put_artifact(f"boundary/{job.trial_id}", boundary)
        db.transition(job.trial_id, "boundary_recorded")
        before_revision = len(session.history)
        revision = run_phase(model=MeteredModel(actor_model, db, spec, job.trial_id,
                             "actor_revision", actor.model_dump(mode="json")),
                             phase="revision", limits=spec.revision,
                             boundary=boundary["message"], **args)
        outcome.phase_results["revision"] = revision
        final_patch = services.patch(baseline, work)
        outcome.final_patch_hash = digest(final_patch)
        outcome.final_tree_hash = tree_hash(work)
        freeze_patch("final", final_patch, outcome.final_tree_hash)
        outcome.metrics["final"] = behavioral_metrics(final_patch, session.history, baseline, work)
        revision_patch = services.patch(draft_workspace, work)
        outcome.metrics["revision"] = behavioral_metrics(revision_patch,
            session.history[before_revision:], draft_workspace, work)
        write_json(directory / "final-session.json", {"step": session.step,
                   "history": session.history, "tree_hash": outcome.final_tree_hash})
        db.freeze_file(directory / "final-session.json")
        db.put_artifact(f"delivery/{job.trial_id}", {
            "boundary_hash": boundary["message_hash"],
            "actor_request_ids": revision["actor_request_ids"],
            "feedback_delivered": "yes" if job.actual_assignment and any(
                db.db.execute("SELECT status FROM calls WHERE call_id=?", (call_id,)).fetchone()[0]
                == "completed" for call_id in revision["actor_request_ids"]) else
            "unknown" if job.actual_assignment and revision["actor_request_ids"] else "no"})
        db.transition(job.trial_id, "final_frozen", {"patch_hash": outcome.final_patch_hash})
        outcome.runtime_status = "failed" if revision["error"] else "completed"
        outcome.error = revision["error"]
        outcome.failure_category = revision["termination"] if revision["error"] else None
    except StudyBudgetExceeded as exc:
        outcome.runtime_status, outcome.error = "budget_stopped", str(exc)
        outcome.failure_category = "study_budget"
    except Exception as exc:
        outcome.error = redact(f"{type(exc).__name__}: {exc}")
        outcome.failure_category = type(exc).__name__
    except BaseException:
        outcome.runtime_status = "interrupted"
        outcome.failure_category = "coordinator_interrupted"
        outcome.error = "Actor attempt interrupted; no inference retry"
        raise
    finally:
        # Submit the last durably accepted workspace after an actor/review failure.
        # If snapshot validation fails, retain an explicitly unknown outcome.
        if outcome.final_patch_hash is None and last_snapshot is not None:
            try:
                patch = (Path(root) / last_snapshot["path"]).read_text()
                if digest(patch) != last_snapshot["patch_hash"]:
                    raise ValueError("Durable snapshot hash mismatch")
                outcome.final_tree_hash = last_snapshot["tree_hash"]
                freeze_patch("final", patch, outcome.final_tree_hash)
                outcome.final_patch_hash = digest(patch)
                outcome.metrics["final"] = behavioral_metrics(patch, session.history)
            except Exception as exc:
                outcome.error = (outcome.error or "") + "; final snapshot unavailable: " + type(exc).__name__
        if event_store:
            event_store.close()
            db.freeze_file(directory / "events.sqlite")
        for model in models:
            try:
                model.close()
            except Exception as exc:
                db.append_event("model_cleanup_error", {"trial_id": job.trial_id,
                    "error": redact(f"{type(exc).__name__}: {exc}")})
        outcome.seconds = time.monotonic() - start
        write_json(directory / "outcome.json", outcome.model_dump(mode="json"))
        db.freeze_file(directory / "outcome.json")
        db.put_artifact(f"outcome/{job.trial_id}", outcome.model_dump(mode="json"))
        db.finish(outcome)
    return outcome


def run_study(root, services=None, max_trials=None):
    plan, spec, tasks, jobs = read_study(root, check_code=True)
    completed = 0
    with coordinator_lock(root), StudyStore(root) as db:
        db.verify(plan["study_id"], jobs)
        db.recover_interrupted()
        while max_trials is None or completed < max_trials:
            assignment = db.claim()
            if assignment is None:
                break
            job = Assignment.model_validate(assignment)
            result = run_trial(root, spec, tasks[job.task_id], job, db, services)
            completed += 1
            if result.runtime_status == "budget_stopped":
                break
        return {"processed": completed, "statuses": {
            status: sum(r["status"] == status for r in db.rows())
            for status in sorted({r["status"] for r in db.rows()})}, "usage": db.usage()}


def audit_study(root, services=None):
    services = services or Services()
    plan, spec, _, jobs = read_study(root, check_code=True)
    count = 0
    with coordinator_lock(root), StudyStore(root) as db:
        db.verify(plan["study_id"], jobs)
        if any(r["status"] in ACTIVE_STATES | {"planned"}
               for r in db.rows()):
            raise ValueError("Deferred audits require the actor batch to finish")
        for job in jobs:
            key = f"audit/{job.trial_id}"
            if not job.shadow_selected or db.artifact(key) is not None:
                continue
            if db.db.execute("SELECT 1 FROM calls WHERE trial_id=? AND role='shadow_audit'",
                             (job.trial_id,)).fetchone():
                db.put_artifact(key, {"status": "interrupted", "trial_id": job.trial_id,
                    "inclusion_probability": spec.shadow_sample_probability,
                    "feedback_delivered": False, "review": None})
                continue
            directory = trial_directory(root, job.trial_id)
            if not (directory / "packet.json").exists():
                db.put_artifact(key, {"status": "unavailable", "trial_id": job.trial_id,
                                     "inclusion_probability": spec.shadow_sample_probability})
                continue
            packet = json.loads((directory / "packet.json").read_text())
            patch_hash = digest((directory / "draft.patch").read_text())
            frozen = db.artifact(f"packet/{job.trial_id}")
            if not frozen or frozen["packet"] != packet or frozen["patch_hash"] != patch_hash:
                raise ValueError("Frozen audit packet/draft changed")
            model = services.model_factory(spec.reviewer.model)
            try:
                record = review_patch(packet, patch_hash,
                    MeteredModel(model, db, spec, job.trial_id, "shadow_audit",
                                 spec.reviewer.model_dump(mode="json")), spec.review)
            finally:
                model.close()
            value = {"status": "done", "trial_id": job.trial_id,
                     "inclusion_probability": spec.shadow_sample_probability,
                     "selection_seed": spec.seed, "draft_patch_hash": patch_hash,
                     "packet_hash": digest(packet),
                     "review": record.model_dump(mode="json"), "feedback_delivered": False}
            write_json(Path(root) / "audit" / f"{job.trial_id}.json", value)
            db.freeze_file(Path(root) / "audit" / f"{job.trial_id}.json")
            db.put_artifact(key, value)
            count += 1
    return {"audits": count}


def grade_study(root, grader=grade_patch):
    plan, spec, tasks, jobs = read_study(root, check_code=True)
    count = 0
    with coordinator_lock(root), StudyStore(root) as db:
        db.verify(plan["study_id"], jobs)
        db.recover_interrupted()
        if any(r["status"] == "planned" for r in db.rows()):
            raise ValueError("Finish the actor batch before independent grading")
        if spec.partition == "confirmation" and db.artifact("gate_lock") is None:
            raise ValueError("Freeze gate calibration before opening confirmation grades")
        outcomes = {r["trial_id"]: json.loads(r["outcome"]) for r in db.rows() if r["outcome"]}
        for job in jobs:
            outcome = outcomes.get(job.trial_id)
            if not outcome or not outcome["final_patch_hash"]:
                continue
            directory = trial_directory(root, job.trial_id)
            patch = (directory / "final.patch").read_text()
            if digest(patch) != outcome["final_patch_hash"]:
                raise ValueError("Final patch changed after submission")
            for attempt in range(1, spec.grader.max_attempts + 1):
                key = f"grade/{job.trial_id}/{attempt}"
                previous = db.artifact(key)
                if previous is not None:
                    if previous["resolved"] is not None:
                        break
                    continue
                identity = digest([plan["study_id"], job.trial_id, digest(patch),
                                   spec.grader.model_dump(), attempt])[:24]
                dest = directory / "grading" / identity
                if dest.exists():
                    # Recover a durable result, or retain the interrupted attempt as unknown.
                    path = dest / "result.json"
                    result = json.loads(path.read_text()) if path.exists() else {
                        "status": "interrupted", "resolved": None, "patch_hash": digest(patch),
                        "harness_identity": spec.grader.identity, "grading_id": identity,
                        "seconds": None}
                else:
                    result = grader(tasks[job.task_id], patch, spec.grader, dest, identity)
                result = GradeRecord.model_validate(result).model_dump(mode="json")
                if (result["patch_hash"] != digest(patch)
                        or result["harness_identity"] != spec.grader.identity
                        or result["grading_id"] != identity):
                    raise ValueError("Grader result identity does not match the frozen submission")
                for filename, expected_hash in result["evidence"].items():
                    path = (dest / filename).resolve()
                    if not path.is_relative_to(dest.resolve()) or file_hash(path) != expected_hash:
                        raise ValueError("Grader evidence changed")
                    db.freeze_file(path)
                if (dest / "result.json").exists():
                    db.freeze_file(dest / "result.json")
                db.put_artifact(key, result)
                count += 1
                if result["resolved"] is not None:
                    break
    return {"grading_attempts": count}
