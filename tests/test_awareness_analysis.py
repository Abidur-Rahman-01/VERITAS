import pytest

from veritas.awareness import ARMS
from veritas.awareness_analysis import factorial_summary
from veritas.awareness_runtime import behavioral_metrics


def rows_for(outcomes=(False, True, False, True), repetitions=1):
    return [{"trial_id": f"{repo}-{task}-{actor}-{rep}-{arm}", "task_id": f"{repo}-{task}",
        "actor_id": actor, "repository_id": repo, "repetition": rep, "arm": arm,
        "runtime_status": "completed", "resolved": outcomes[k]}
        for repo in ("a", "b", "c") for task in (1, 2) for actor in ("one", "two")
        for rep in range(repetitions) for k, arm in enumerate(ARMS)]


def test_known_factorial_contrasts_and_repository_pairing():
    report = factorial_summary(rows_for(), repetitions=100)
    expected = {"awareness": 1, "feedback": 0, "feedback_cued": 0, "interaction": 0, "combined": 1}
    for name, value in expected.items():
        assert report["contrasts"][name]["estimate"] == value
        assert report["contrasts"][name]["confidence_interval"] == [value, value]
    assert report["repositories"] == 3
    assert report["contrasts"]["interaction"]["alpha"] == 0.0125


def test_missing_grade_stays_in_assigned_population():
    rows = rows_for()
    for row in rows:
        if row["arm"] == "10":
            row["resolved"] = None
    report = factorial_summary(rows, repetitions=100)
    effect = report["contrasts"]["awareness"]
    assert effect["estimate"] is None
    assert effect["missingness_bounds"] == [0, 1]
    assert effect["system_success_estimate"] == 0
    assert report["cells"]["10"]["unknown"] == report["cells"]["10"]["assigned"]


def test_repetition_count_cannot_reweight_a_task():
    rows = rows_for()
    duplicates = []
    for row in rows:
        if row["task_id"] == "a-1":
            row["resolved"] = False
            for rep in range(1, 5):
                duplicates.append({**row, "repetition": rep, "trial_id": f"{row['trial_id']}-{rep}"})
    before = factorial_summary(rows, repetitions=100)
    after = factorial_summary(rows + duplicates, repetitions=100)
    for name in before["contrasts"]:
        for key in ("estimate", "confidence_interval", "missingness_bounds"):
            assert before["contrasts"][name][key] == pytest.approx(after["contrasts"][name][key])


def test_incomplete_or_legacy_treatment_is_rejected():
    with pytest.raises(ValueError, match="Incomplete"):
        factorial_summary(rows_for()[1:], repetitions=100)
    rows = rows_for()
    rows[0]["arm"] = None
    with pytest.raises(ValueError, match="four-cell"):
        factorial_summary(rows, repetitions=100)


def test_empty_language_and_unavailable_test_extraction_are_missing():
    value = behavioral_metrics("", [])
    assert value["hedging_rate"] is None
    assert value["test_functions_added"] is None
    assert value["defensive_test_count"] is None
    assert value["self_reported_confidence"] is None
