import sqlite3

import numpy as np
import pytest

from veritas.calibration import calibration_metrics, fit_artifact, fit_temperature
from veritas.critic import critic_text, score_records, train_linear
from veritas.io import read_records, write_jsonl
from veritas.replay import eligible_records, evaluate, paired_bootstrap, sweep, tune
from veritas.schema import StepRecord
from veritas.store import EventStore, export_ledger, verify_export


def test_temperature_improves_overconfidence():
    z = np.array([-5, -5, 5, 5] * 20)
    y = np.array([0, 1, 0, 1] * 20)
    temperature = fit_temperature(z, y)
    assert calibration_metrics(z, y, temperature)["nll"] < calibration_metrics(z, y)["nll"]


def test_single_class_rejected():
    with pytest.raises(ValueError):
        fit_temperature([-1, -2], [0, 0])


def test_critic_features_cannot_leak_outcome(step):
    row = step()
    text = critic_text(row)
    row.update(
        error_label=1,
        verification={"verdict": "FAIL"},
        observation="outcome",
        p_error=1,
        private={"answer": "hidden"},
    )
    assert critic_text(row) == text


def test_event_store_export_roundtrip_and_immutability(tmp_path, step):
    store = EventStore(tmp_path / "events.db")
    store.append(StepRecord.model_validate(step()))
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute("DELETE FROM events")
    store.db.rollback()
    store.close()
    export_ledger(tmp_path / "events.db", tmp_path / "export")
    assert verify_export(tmp_path / "export")["rows"] == 1
    assert list(read_records(tmp_path / "export/events.parquet")) == list(
        read_records(tmp_path / "export/events.jsonl")
    )
    with (tmp_path / "export/events.jsonl").open("a") as f:
        f.write("tampered")
    with pytest.raises(ValueError):
        verify_export(tmp_path / "export")


def test_encrypted_export(tmp_path, monkeypatch, step):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("TEST_EXPORT_KEY", Fernet.generate_key().decode())
    store = EventStore(tmp_path / "events.db")
    store.append(StepRecord.model_validate(step()))
    store.close()
    export_ledger(tmp_path / "events.db", tmp_path / "export", "TEST_EXPORT_KEY")
    assert not (tmp_path / "export/events.jsonl").exists()
    assert verify_export(tmp_path / "export")["encrypted"]


def test_verifier_is_not_ground_truth(step):
    rows = [
        step(0, verification={"verdict": "FAIL", "reason": "false alarm"}),
        step(1, verification={"verdict": "PASS", "reason": "missed error"}),
    ]
    result, _ = evaluate(rows, "always", 1)
    assert result["errors_caught"] == 0
    assert result["false_rejections"] == 1
    assert result["true_errors_verified"] == 1


def test_full_analysis_pipeline_without_models(tmp_path, step):
    rows = []
    for role, offset in [("critic_train", 0), ("probability", 20), ("verifier_stats", 40)]:
        rows += [step(i, split="calib", calibration_role=role) for i in range(offset, offset + 20)]
    rows += [step(i, split="val") for i in range(60, 70)]
    rows += [step(i, split="test") for i in range(70, 80)]
    path = tmp_path / "records.jsonl"
    write_jsonl(path, rows)
    artifact_path = tmp_path / "calibration.json"
    artifact = fit_artifact(path, artifact_path)
    assert artifact["statistics"]["final_answer"]["detection_rate"] == 1
    tuning_path = tmp_path / "tuning.json"
    tune(path, artifact_path, tuning_path, [0.02, 0.04])
    result = sweep(path, artifact_path, tuning_path, tmp_path / "report", [0.02, 0.04])
    assert len(result) == 16
    assert all(r["budget_violation_rate"] == 0 for r in result)
    from veritas.report import frontier_report

    frontier_report(tmp_path / "report")
    assert (tmp_path / "report/frontier.png").stat().st_size > 1000
    # Tiny classifier fit is a software test, not an experiment or local LLM execution.
    train_linear(path, tmp_path / "critic")
    score_records(path, tmp_path / "critic", tmp_path / "scored.jsonl")
    assert len(list(read_records(tmp_path / "scored.jsonl"))) == 80


def test_missing_labels_cannot_replay(tmp_path, step):
    write_jsonl(tmp_path / "records.jsonl", [step(error_label=None)])
    with pytest.raises(ValueError, match="independent labels"):
        eligible_records(tmp_path / "records.jsonl", {"fit_groups": []}, "test")


def test_task_leakage_rejected(tmp_path, step):
    rows = [step(i, split="calib", calibration_role="probability") for i in range(12)]
    rows.append(step(20, group_id="task-0", split="test"))
    write_jsonl(tmp_path / "records.jsonl", rows)
    with pytest.raises(ValueError, match="leakage"):
        fit_artifact(tmp_path / "records.jsonl", tmp_path / "artifact.json")


def test_bootstrap_pairs_tasks(step):
    rows = [step(i) for i in range(10)]
    _, a = evaluate(rows, "always", 1)
    _, b = evaluate(rows, "never", 1)
    result = paired_bootstrap(a, b, repetitions=50)
    assert result["mean_difference_per_task"] == 0.5
    assert result["ci95"][0] >= 0
