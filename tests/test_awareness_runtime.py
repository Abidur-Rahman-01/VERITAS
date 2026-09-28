import json
from dataclasses import replace

import pytest

from veritas.awareness import DisclosurePolicy, read_study
from veritas.awareness_analysis import study_rows
from veritas.awareness_runtime import audit_study, run_study, trial_directory
from veritas.awareness_store import StudyStore
from veritas.context import phase_context
from veritas.io import digest
from veritas.schema import Usage
from veritas.store import EventStore


@pytest.mark.parametrize("compact", [False, True])
def test_all_arms_continue_with_equal_limits_and_isolated_workspaces(awareness_setup, compact):
    f = awareness_setup
    root = f.create(compact=compact)
    result = run_study(root, f.services)
    assert result["statuses"] == {"completed": 4}
    assert len(set(f.workspaces)) == 4
    _, _, _, jobs = read_study(root)
    draft_prompts = {}
    for job in jobs:
        directory = trial_directory(root, job.trial_id)
        assert "value = 1" in (directory / "draft.patch").read_text()
        assert "value = 2" in (directory / "final.patch").read_text()
        outcome = json.loads((directory / "outcome.json").read_text())
        assert outcome["phase_results"]["draft"]["steps"] == 2
        assert outcome["phase_results"]["revision"]["steps"] == 2
        store = EventStore(directory / "events.sqlite")
        records = list(store.records())
        store.close()
        assert [r.step_id for r in records] == [0, 1, 2, 3]
        assert all(r.schema_version == 2 and r.trial_id == job.trial_id for r in records)
        for r in records:
            context = json.loads(r.context)
            assert ("initial_session_notice" in context) == job.disclosure_assigned
            assert "PRIVATE_GOLD" not in r.context and "PRIVATE_TEST" not in r.context
            assert "actual_assignment" not in r.context
            request = json.loads((root / "calls" / f"{r.actor_request_id:08d}.json").read_text())
            assert r.prompt_hash == request["prompt_hash"] == digest(request["messages"])
        draft_prompts[job.arm] = [r.context for r in records if r.phase == "draft"]
        boundary = json.loads((directory / "review.json").read_text())
        assert (boundary["review"] is not None) == job.actual_assignment
        assert ('"verdict": "PASS"' in boundary["message"]) == job.actual_assignment
    assert draft_prompts["00"] == draft_prompts["01"]
    assert draft_prompts["10"] == draft_prompts["11"]
    reviewer_calls = [r for r in f.requests if r["model"] == "reviewer"]
    assert len(reviewer_calls) == 2
    before = {j.trial_id: (trial_directory(root, j.trial_id) / "final.patch").read_text() for j in jobs}
    assert audit_study(root, f.services)["audits"] == 2
    assert audit_study(root, f.services)["audits"] == 0
    assert before == {j.trial_id: (trial_directory(root, j.trial_id) / "final.patch").read_text() for j in jobs}
    assert run_study(root, f.services)["processed"] == 0


@pytest.mark.parametrize("compact", [False, True])
def test_cue_and_boundary_survive_history_trimming(awareness_setup, compact):
    task = awareness_setup.tasks[0]
    cue = DisclosurePolicy().render()
    history = [{"action": {"tool": "write_file", "args": {"content": "x"*20000}},
                "observation": {"content": "y"*20000}}] * 20
    text = phase_context(task, history, phase="revision", cue=cue, boundary="KEEP_THIS_BOUNDARY",
        history_chars=1000, observation_chars=200, compact=compact, steps_remaining=2, input_chars=1500)
    assert len(text) <= 1500
    assert text.count(cue) == 1
    assert "KEEP_THIS_BOUNDARY" in text
    assert len(history) == 20


def test_review_failure_still_delivers_equal_revision_opportunity(awareness_setup):
    f = awareness_setup

    class BrokenReviewer(f.model):
        def complete(self, system, user, **kwargs):
            if self.config.name == "reviewer":
                raise TimeoutError("fixture timeout")
            return super().complete(system, user, **kwargs)

    root = f.create()
    run_study(root, replace(f.services, model_factory=BrokenReviewer))
    _, _, rows = study_rows(root)
    assert all(r["runtime_status"] == "completed" for r in rows)
    for row in rows:
        if row["actual_assignment"]:
            assert row["verifier_attempted"] and not row["verifier_completed"]
            assert row["feedback_delivered"] == "yes"
            assert row["deployed_tokens"] is None
            assert row["review_verdict"] == "ERROR"


def test_unknown_actor_usage_stops_and_retains_failure(awareness_setup):
    f = awareness_setup

    class UnknownUsage(f.model):
        def complete(self, system, user, **kwargs):
            raw, _ = super().complete(system, user, **kwargs)
            return raw, Usage(measured=False)

    root = f.create()
    result = run_study(root, replace(f.services, model_factory=UnknownUsage))
    assert result["statuses"] == {"failed": 4}
    assert result["usage"]["actor_draft"]["unknown_calls"] == 4
    _, _, rows = study_rows(root)
    assert all(r["resolved"] is None and r["deployed_tokens"] is None for r in rows)


def test_remaining_output_budget_caps_calls(awareness_setup):
    f = awareness_setup
    root = f.create(draft={"steps": 3, "completion_tokens": 7, "seconds": 30},
                    revision={"steps": 3, "completion_tokens": 7, "seconds": 30})

    class CappedModel(f.model):
        def complete(self, system, user, **kwargs):
            raw, usage = super().complete(system, user, **kwargs)
            usage.completion_tokens = min(4, kwargs["max_tokens"])
            return raw, usage

    run_study(root, replace(f.services, model_factory=CappedModel))
    caps = [r["cap"] for r in f.requests if r["model"] == "actor"]
    assert caps == [7, 3, 7, 3] * 4


def test_durable_recovery_never_reruns_actor(awareness_setup):
    f = awareness_setup
    root = f.create()
    plan, _, _, jobs = read_study(root)
    run_study(root, f.services, max_trials=1)
    with StudyStore(root) as db:
        job = db.claim()
        assert job is not None
        db.recover_interrupted()
        row = next(r for r in db.rows() if r["trial_id"] == job["trial_id"])
        assert row["status"] == "interrupted"
        assert json.loads(row["outcome"])["seconds"] is None
        with pytest.raises(ValueError, match="Invalid trial transition"):
            db.transition(job["trial_id"], "running")
        db.verify(plan["study_id"], jobs)
    assert run_study(root, f.services)["processed"] == 2


def test_artifact_tampering_is_detected(awareness_setup):
    root = awareness_setup.create()
    run_study(root, awareness_setup.services, max_trials=1)
    plan, _, _, jobs = read_study(root)
    patch = trial_directory(root, jobs[0].trial_id) / "final.patch"
    patch.write_text("tampered")
    with StudyStore(root) as db, pytest.raises(ValueError, match="Frozen study artifact changed"):
        db.verify(plan["study_id"], jobs)
