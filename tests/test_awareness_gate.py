import numpy as np
import pytest

from veritas.awareness_gate import _repository_metrics, calibrate_gate, fit_gate, report_gate
from veritas.awareness_grading import GradeRecord
from veritas.awareness_runtime import grade_study, run_study
from veritas.io import digest


def test_declined_unknown_outcomes_have_zero_risk_and_coverage():
    rows = [{"trial_id": "x", "repository_id": "repo", "resolved": None}]
    assert np.array_equal(_repository_metrics(rows, {"x": 0.1}, None), [[0, 0, 0]])
    assert np.array_equal(_repository_metrics(rows, {"x": None}, 1.0), [[0, 0, 0]])
    assert np.array_equal(_repository_metrics(rows, {"x": 0.1}, 1.0), [[0, 1, 1]])


def test_calibration_is_locked_before_confirmation_grades(awareness_setup, tmp_path):
    f = awareness_setup
    actors = [f.spec.actors[0].model_dump(mode="json"),
              {**f.spec.actors[0].model_dump(mode="json"), "id": "second", "family": "other"}]
    settings = {"actors": actors, "preregistration": "fixture-frozen-analysis",
                "image_digests": {t.private["instance_id"]: "sha256:" + "b"*64 for t in f.tasks}}
    development = f.create(**settings)
    calibration = f.create(partition="calibration", **settings)
    confirmation = f.create(partition="confirmation", **settings)

    def grader(task, patch, spec, directory, identity):
        return GradeRecord(status="resolved", resolved=True, patch_hash=digest(patch),
            harness_identity=spec.identity, grading_id=identity, seconds=0).model_dump(mode="json")

    for root in (development, calibration, confirmation):
        run_study(root, f.services)
    for root in (development, calibration):
        grade_study(root, grader)
    with pytest.raises(ValueError, match="Freeze gate calibration"):
        grade_study(confirmation, grader)
    scorer, gate = tmp_path / "score.json", tmp_path / "gate.json"
    fit_gate(development, scorer)
    frozen = calibrate_gate(scorer, calibration, confirmation, gate)
    assert frozen["population_certification"] is False
    assert all(p["chosen"]["threshold"] is None for p in frozen["policies"])
    # No certification is possible from one repository at this target. Defer-all
    # remains well-defined even before confirmation's grades are available.
    report = report_gate(gate, confirmation)
    assert all(e["coverage"] == 0 and e["risk"] == 0 and e["conditional_failure"] is None
               for e in report["estimates"])
    grade_study(confirmation, grader)
    with pytest.raises(ValueError, match="already opened"):
        calibrate_gate(scorer, calibration, confirmation, tmp_path / "late.json")
