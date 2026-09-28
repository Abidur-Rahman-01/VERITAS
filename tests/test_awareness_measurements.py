import json
import difflib
from dataclasses import replace

import pytest

from veritas.awareness import DisclosurePolicy, StudyProtocol, plan_study, read_study
from veritas.awareness_analysis import report_study, study_rows
from veritas.awareness_grading import GradeRecord
from veritas.awareness_measurements import (
    ConfidenceResponse,
    classify_intent,
    extract_tests,
    intent_packet,
    measure_study,
)
from veritas.awareness_runtime import grade_study, run_study, trial_directory
from veritas.awareness_store import StudyStore
from veritas.io import digest
from veritas.schema import Usage


def test_ast_qualified_names_decorators_and_unknown_languages(tmp_path):
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    (before / "test_case.py").write_text("class TestA:\n    def test_same(self):\n        assert 1\n")
    (after / "test_case.py").write_text(
        "class TestA:\n    def test_same(self):\n        assert 2\n"
        "class TestB:\n    @parametrize('x', [0, 1])\n    async def test_same(self, x):\n"
        "        assert x >= 0\n        def test_helper():\n            pass\n")
    patch = "--- a/test_case.py\n+++ b/test_case.py\n"
    value = extract_tests(patch, before, after)
    assert value["test_functions_added"] == value["test_functions_modified"] == 1
    assert {t["name"] for t in value["test_candidates"]} == {"TestA.test_same", "TestB.test_same"}
    assert "@parametrize" in value["test_candidates"][1]["after"]
    unknown = extract_tests(patch + "+++ b/file.test.js\n", before, after)
    assert unknown["test_functions_added"] is None
    assert not unknown["test_extraction_complete"]


def test_parse_failure_and_symlink_do_not_become_zero_tests(tmp_path):
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    (after / "test_bad.py").write_text("def test_broken(\n")
    result = extract_tests("+++ b/test_bad.py", before, after)
    assert result["test_functions_added"] is None
    (after / "tests").symlink_to(before, target_is_directory=True)
    result = extract_tests("+++ b/tests/test_external.py", before, after)
    assert result["test_extraction_gaps"]


def test_intent_requires_code_evidence_and_preserves_uncertainty(awareness_setup):
    metrics = {"test_candidates": [{"id": "a", "after": "assert len([]) == 0", "before": ""},
                                   {"id": "b", "after": "assert x", "before": ""}],
               "test_extraction_complete": True}
    packet = intent_packet(awareness_setup.tasks[0], metrics, awareness_setup.spec.defensive_tests)
    labels = {"tests": [{"id": "a", "label": "edge_case", "evidence": "len([]) == 0", "reason": "empty"},
                        {"id": "b", "label": "uncertain", "evidence": "", "reason": "unknown x"}]}
    result = classify_intent(json.dumps(labels), packet, metrics)
    assert result["defensive_test_count"] is None
    assert result["defensive_test_lower_bound"] == 1
    labels["tests"][0]["evidence"] = "made up"
    with pytest.raises(ValueError, match="exact code"):
        classify_intent(json.dumps(labels), packet, metrics)
    labels["tests"] = labels["tests"][1:]
    with pytest.raises(ValueError, match="exactly once"):
        classify_intent(json.dumps(labels), packet, metrics)


@pytest.mark.parametrize("confidence", [True, False, "0.8", -0.1, 1.1, float("nan")])
def test_confidence_rejects_invalid_probabilities(confidence):
    with pytest.raises(ValueError):
        ConfidenceResponse(confidence=confidence)


def test_neutral_control_is_explicit_and_preserved_in_both_phases(awareness_setup):
    f = awareness_setup
    neutral = "n" * len(DisclosurePolicy().render())
    with pytest.raises(ValueError, match="Primary control"):
        StudyProtocol.model_validate({**f.spec.model_dump(), "neutral_control_text": neutral})
    with pytest.raises(ValueError, match="match disclosure length"):
        f.create(control="neutral_length_matched", neutral_control_text="short")
    root = f.create(control="neutral_length_matched", neutral_control_text=neutral)
    run_study(root, f.services)
    for request in f.requests:
        if request["model"] == "actor":
            assert json.loads(request["user"])["initial_session_notice"] in (neutral, DisclosurePolicy().render())
    report = report_study(root)
    assert report["control"] == "neutral_length_matched"


def test_deferred_measurements_are_isolated_metered_and_idempotent(awareness_setup):
    f = awareness_setup
    root = f.create(confidence={"enabled": True}, defensive_tests={"enabled": True})
    with pytest.raises(ValueError, match="actor batch"):
        measure_study(root, f.services)
    run_study(root, f.services)
    plan, _, _, jobs = read_study(root)
    finals = {j.trial_id: (trial_directory(root, j.trial_id) / "final.patch").read_bytes() for j in jobs}
    before = len(f.requests)

    class ConfidenceModel(f.model):
        def complete(self, system, user, **kwargs):
            assert "Post-task confidence" in system
            assert "PRIVATE_GOLD" not in user and "PRIVATE_TEST" not in user
            assert "resolved" not in user and "actual_assignment" not in user
            assert "value = 2" in json.loads(user)["submitted_patch"]
            return '{"confidence": 0.75}', Usage(prompt_tokens=4, completion_tokens=4)

    services = replace(f.services, model_factory=ConfidenceModel)
    assert measure_study(root, services)["measurements"] == 16
    assert measure_study(root, services)["measurements"] == 0
    assert len(f.requests) == before
    _, _, rows = study_rows(root)
    assert all(r["measurement_model_calls"] == 1 for r in rows)
    assert all(r["outcome"]["metrics"]["final"]["self_reported_confidence"] == .75 for r in rows)
    assert all(r["outcome"]["metrics"]["draft"]["self_reported_confidence"] is None for r in rows)
    assert all(r["outcome"]["metrics"]["draft"]["defensive_test_count"] == 0 for r in rows)
    assert finals == {j.trial_id: (trial_directory(root, j.trial_id) / "final.patch").read_bytes() for j in jobs}
    with StudyStore(root) as db:
        db.verify(plan["study_id"], jobs)


def test_interrupted_measurement_is_not_retried(awareness_setup):
    f = awareness_setup
    root = f.create(confidence={"enabled": True})
    run_study(root, f.services)
    _, spec, _, jobs = read_study(root)
    with StudyStore(root) as db:
        db.reserve_call(jobs[0].trial_id, "confidence_final", 20, spec)
    measure_study(root, f.services)
    with StudyStore(root) as db:
        assert db.artifact(f"measurement/confidence/{jobs[0].trial_id}/final")["status"] == "interrupted"
        assert db.usage(jobs[0].trial_id)["confidence_final"]["calls"] == 1


def test_intent_model_receives_only_blinded_public_test_evidence(awareness_setup):
    f = awareness_setup
    root = f.create(defensive_tests={"enabled": True})
    observed = []

    class IntentModel(f.model):
        def complete(self, system, user, **kwargs):
            if "Blinded defensive-test intent" in system:
                packet = json.loads(user)
                observed.append(packet)
                assert set(packet) == {"task", "tests"}
                assert "PRIVATE_" not in user and "initial_notice" not in user
                return json.dumps({"tests": [{"id": test["id"], "label": "edge_case",
                    "evidence": "assert len([]) == 0", "reason": "empty input"}
                    for test in packet["tests"]]}), Usage(prompt_tokens=4, completion_tokens=4)
            if self.config.name == "actor" and json.loads(user)["steps_remaining"] == 3:
                return json.dumps({"tool": "write_file", "args": {"path": "test_empty.py",
                    "content": "def test_empty():\n    assert len([]) == 0\n"}}), Usage(
                        prompt_tokens=4, completion_tokens=4)
            return super().complete(system, user, **kwargs)

    def patch(before, after):
        from pathlib import Path

        old, new = Path(before) / "test_empty.py", Path(after) / "test_empty.py"
        diff = "".join(difflib.unified_diff(old.read_text().splitlines(True) if old.exists() else [],
            new.read_text().splitlines(True) if new.exists() else [],
            fromfile="a/test_empty.py", tofile="b/test_empty.py"))
        return f.services.patch(before, after) + diff

    services = replace(f.services, model_factory=IntentModel, patch=patch)
    run_study(root, services)
    measure_study(root, services)
    assert len(observed) == 8  # Four draft + four final; no changed revision tests.
    _, _, rows = study_rows(root)
    assert all(row["outcome"]["metrics"]["draft"]["defensive_test_count"] == 1 for row in rows)
    assert all(row["outcome"]["metrics"]["revision"]["defensive_test_count"] == 0 for row in rows)


def test_draft_grading_is_separate_selected_and_never_overwrites_final(awareness_setup):
    f = awareness_setup
    root = f.create(draft_grade_probability=1)
    run_study(root, f.services)
    identities = set()

    def grader(task, patch, spec, directory, identity):
        assert identity not in identities
        identities.add(identity)
        resolved = "value = 2" in patch
        return GradeRecord(status="resolved" if resolved else "unresolved", resolved=resolved,
            patch_hash=digest(patch), harness_identity=spec.identity, grading_id=identity, seconds=2).model_dump()

    assert grade_study(root, grader, phase="draft")["grading_attempts"] == 4
    assert grade_study(root, grader, phase="draft")["grading_attempts"] == 0
    _, _, rows = study_rows(root)
    assert all(r["draft_resolved"] is False and r["resolved"] is None for r in rows)
    assert grade_study(root, grader)["grading_attempts"] == 4
    _, _, rows = study_rows(root)
    assert all(r["resolved"] is True and r["draft_resolved"] is False for r in rows)
    assert all(r["grade_seconds"] == 4 for r in rows)
    assert report_study(root)["draft_grading"]["selected"] == 4
    default = f.create()
    run_study(default, f.services)
    assert grade_study(default, grader, phase="draft")["grading_attempts"] == 0


def test_draft_sampling_selects_complete_blocks_without_changing_assignment_stream(awareness_setup):
    f = awareness_setup
    spec = f.spec.model_copy(update={"repetitions": 30, "draft_grade_probability": .5})
    jobs = plan_study(spec, f.tasks, f.splits)[1]
    selected = [j for j in jobs if j.draft_grade_selected]
    assert 0 < len(selected) < len(jobs)
    for block in {j.block_id for j in jobs}:
        assert len({j.draft_grade_selected for j in jobs if j.block_id == block}) == 1
    without = plan_study(spec.model_copy(update={"draft_grade_probability": 0}), f.tasks, f.splits)[1]
    schedule = lambda jobs: [(j.task_id, j.actor_id, j.repetition, j.arm, j.slot, j.order,
                              j.shadow_selected) for j in jobs]
    assert schedule(jobs) == schedule(without)
