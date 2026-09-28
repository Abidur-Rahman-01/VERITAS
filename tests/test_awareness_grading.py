import json
from types import SimpleNamespace

import pytest

from veritas.awareness import GraderSpec, read_study
from veritas.awareness_grading import GradeRecord, grade_patch, parse_grade
from veritas.awareness_runtime import grade_study, run_study
from veritas.awareness_store import StudyStore
from veritas.io import digest, write_json


@pytest.mark.parametrize("field,status,resolved", [
    ("resolved_ids", "resolved", True),
    ("unresolved_ids", "unresolved", False),
    ("empty_patch_ids", "invalid_patch", False),
    ("error_ids", "infrastructure_error", None),
    ("incomplete_ids", "ungraded", None),
])
def test_pinned_schema_two_outcome_categories(field, status, resolved):
    # Field names mirror make_run_report() in the pinned d307ff9f SWE-ReBench fork.
    report = {"schema_version": 2, "resolved_ids": [], "unresolved_ids": [],
              "empty_patch_ids": [], "error_ids": [], "incomplete_ids": [], field: ["fixture"]}
    assert parse_grade(report, "fixture") == {"status": status, "resolved": resolved}


def test_conflicting_or_malformed_grades_are_not_success():
    with pytest.raises(ValueError, match="Conflicting"):
        parse_grade({"resolved_ids": ["x"], "error_ids": ["x"]}, "x")
    with pytest.raises(ValueError, match="schema"):
        parse_grade({"resolved_ids": "x"}, "x")
    result = parse_grade({"unresolved_ids": ["x"]}, "x", {"x": {
        "resolved": False, "patch_exists": True, "patch_successfully_applied": False}})
    assert result == {"status": "infrastructure_error", "resolved": None}
    with pytest.raises(ValueError, match="disagree"):
        GradeRecord(status="infrastructure_error", resolved=False, patch_hash="patch",
                    harness_identity="fixture", grading_id="id")


def test_independent_grader_records_raw_evidence(awareness_setup, tmp_path):
    task = awareness_setup.tasks[0]
    spec = GraderSpec(identity="fixture", package_sha256="f"*64)

    def execute(argv, *, cwd, **kwargs):
        assert kwargs["check"] is False
        assert "PRIVATE_GOLD" not in " ".join(argv)
        predictions = json.loads((cwd / "prediction.jsonl").read_text())
        assert predictions["model_name_or_path"] == "candidate"
        write_json(cwd / "candidate.opaque.json", {"schema_version": 2,
                   "resolved_ids": [task.private["instance_id"]], "unresolved_ids": []})
        return SimpleNamespace(returncode=0)

    result = grade_patch(task, "a patch", spec, tmp_path / "grade", "opaque", execute=execute)
    assert result["status"] == "resolved"
    assert result["prediction_hash"] and result["report_hash"] and result["dataset_hash"]
    assert "candidate.opaque.json" in result["evidence"]


def test_exit_zero_without_report_is_infrastructure_failure(awareness_setup, tmp_path):
    spec = GraderSpec(identity="fixture", package_sha256="f"*64)
    result = grade_patch(awareness_setup.tasks[0], "patch", spec, tmp_path / "grade", "opaque",
                         execute=lambda *args, **kwargs: SimpleNamespace(returncode=0))
    assert result["status"] == "infrastructure_error" and result["resolved"] is None


def test_empty_patch_is_unresolved_without_harness(awareness_setup, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("Empty patches must not launch a grader")

    result = grade_patch(awareness_setup.tasks[0], "", awareness_setup.spec.grader,
                         tmp_path / "grade", "opaque", execute=forbidden)
    assert result["status"] == "invalid_patch" and result["resolved"] is False


def test_grading_retries_only_unknown_results_without_actor_calls(awareness_setup):
    f = awareness_setup
    root = f.create()
    run_study(root, f.services)
    actor_calls = len(f.requests)
    ids, attempts = set(), {}

    def grader(task, patch, spec, directory, identity):
        assert identity not in ids
        ids.add(identity)
        attempt = attempts.get(task.task_id, 0)
        attempts[task.task_id] = attempt + 1
        return GradeRecord(status="infrastructure_error" if attempt % 2 == 0 else "unresolved",
            resolved=None if attempt % 2 == 0 else False, patch_hash=digest(patch),
            harness_identity=spec.identity, grading_id=identity, seconds=1).model_dump(mode="json")

    assert grade_study(root, grader)["grading_attempts"] == 8
    assert grade_study(root, grader)["grading_attempts"] == 0
    assert len(f.requests) == actor_calls
    plan, _, _, jobs = read_study(root)
    with StudyStore(root) as db:
        db.verify(plan["study_id"], jobs)
        assert all(db.artifact(f"grade/{j.trial_id}/2")["resolved"] is False for j in jobs)
