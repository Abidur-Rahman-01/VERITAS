"""Stage 6 pilot fixtures; scheduling checks only, not experimental evidence."""

import json
from pathlib import Path

import pytest
import yaml
from test_dependency_cohort import review
from test_dependency_scope import prepared, task

from veritas.cli import dispatch, parser
from veritas.dependency_cohort import finalize_cohort, prepare_reviews
from veritas.dependency_pilot import create_pilot, pilot_rows, read_pilot, run_pilot
from veritas.dependency_scope import create_scope
from veritas.io import read_jsonl, write_json, write_jsonl


def cohort_fixture(tmp_path):
    data = prepared(tmp_path / "data", [task("a"), task("b"), task("c")])
    scope = tmp_path / "scope"
    create_scope(data, scope)
    review_dir = tmp_path / "reviews"
    prepare_reviews(scope, review_dir)
    annotations = list(read_jsonl(review_dir / "annotations.jsonl"))
    for row in annotations:
        row["reviews"] = [review("reviewer-one"), review("reviewer-two")]
    write_jsonl(review_dir / "annotations.jsonl", annotations)
    protocol = json.loads(Path("configs/dependency-protocol.example.json").read_text())
    protocol.update(
        actor_identity="fixture actor",
        verifier_identity="fixture verifier",
        trigger_a="first interface edit",
        trigger_b="first caller edit",
        feedback_and_repair="single verifier diagnostic then repair",
        grading_protocol="upstream independent SWE grading",
        meaningful_effect=0.1,
        outcome_blind_freeze=True,
    )
    write_json(tmp_path / "protocol.json", protocol)
    cohort = tmp_path / "cohort"
    finalize_cohort(
        scope=scope,
        tasks=data,
        reviews=review_dir / "annotations.jsonl",
        protocol=tmp_path / "protocol.json",
        config="configs/experiment.yaml",
        output=cohort,
    )
    return data, cohort


def pilot_config(tmp_path, data, cohort, **updates):
    config = {
        "tasks": str(data),
        "cohort": str(cohort),
        "base_config": "configs/experiment.yaml",
        "partition": "discovery",
        "limit": 1,
    }
    config.update(updates)
    path = tmp_path / "pilot.yaml"
    path.write_text(yaml.safe_dump(config))
    return path


def test_pilot_freezes_balanced_randomized_four_arm_schedule(tmp_path):
    data, cohort = cohort_fixture(tmp_path)
    output = tmp_path / "pilot"
    plan = create_pilot(pilot_config(tmp_path, data, cohort), output)
    assert plan["job_count"] == 12
    assert {job["arm"] for job in plan["jobs"]} == {"00", "10", "01", "11"}
    assert plan["execution_order"] != sorted(plan["execution_order"])
    assert all(job["target_identity"] == "api.py::interface" for job in plan["jobs"])
    assert all(job["caller_identity"] == "caller.py::caller" for job in plan["jobs"])
    assert read_pilot(output)["pilot_id"] == plan["pilot_id"]
    plan["job_count"] = 99
    write_json(output / "pilot.json", plan)
    with pytest.raises(ValueError, match="Pilot plan changed"):
        read_pilot(output)


def test_pilot_resume_report_retains_never_reached_b(tmp_path, monkeypatch):
    data, cohort = cohort_fixture(tmp_path)
    output = tmp_path / "pilot"
    config = pilot_config(tmp_path, data, cohort)
    create_pilot(config, output)
    calls = []

    def fake_collect(tasks, runtime_config, destination, **kwargs):
        calls.append((runtime_config.seed, runtime_config.opportunities.mode))
        assert runtime_config.run.policy == "never"
        assert runtime_config.run.score_critic is False
        assert runtime_config.opportunities.target_identity == "api.py::interface"
        Path(destination).mkdir(parents=True, exist_ok=True)
        write_jsonl(
            Path(destination) / "summaries.jsonl",
            [
                {
                    "task_success": True,
                    "total_online_tokens": 10,
                    "audit_tokens": 0,
                    "token_usage_complete": True,
                    "opportunity_observation": {
                        "events": {
                            "A": {"status": "skipped", "decision_reason": "shadow_observation_only"},
                            "B": {"status": "never_triggered", "step": None},
                        }
                    },
                }
            ],
        )

    monkeypatch.setattr("veritas.runtime.collect", fake_collect)
    rows = run_pilot(output)
    assert len(calls) == 12
    assert len(rows) == 4
    assert all(row["scheduled"] == 3 for row in rows)
    assert all(row["done"] == 3 and row["complete"] for row in rows)
    assert all(row["triggered_A"] == 3 for row in rows)
    assert all(row["never_reached_B"] == 3 for row in rows)
    assert all(row["opportunity_policy_execution"] == "shadow_trigger_detection_only" for row in rows)
    run_pilot(output)
    assert len(calls) == 12
    assert (output / "pilot-results.csv").exists()
    assert pilot_rows(output) == rows


def test_dependency_pilot_cli_plan_and_report(tmp_path, monkeypatch):
    data, cohort = cohort_fixture(tmp_path)
    output = tmp_path / "pilot"
    config = pilot_config(tmp_path, data, cohort)
    dispatch(parser().parse_args(["dependency-pilot", "--config", str(config), "--output", str(output)]))
    assert (output / "pilot.json").exists()

    def fake_rows(_output):
        return [{"arm": "00", "source": "fixture", "scheduled": 1}]

    monkeypatch.setattr("veritas.dependency_pilot.report_pilot", fake_rows)
    result = dispatch(
        parser().parse_args([
            "dependency-pilot",
            "--config",
            str(config),
            "--output",
            str(output),
            "--report",
        ])
    )
    assert result == [{"arm": "00", "source": "fixture", "scheduled": 1}]
