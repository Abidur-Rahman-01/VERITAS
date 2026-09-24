from veritas.diagnostics import diagnose_run
from veritas.io import write_json, write_jsonl
from veritas.schema import StepRecord
from veritas.store import EventStore


def test_diagnostic_distinguishes_scope_and_constant_scores(tmp_path, step):
    store = EventStore(tmp_path / "events.sqlite")
    for i in range(3):
        store.append(
            StepRecord.model_validate(
                step(
                    i,
                    raw_logit=-9.21,
                    split="calib",
                    calibration_role="probability",
                    label_scope="operational" if i == 2 else "semantic",
                )
            )
        )
    store.close()
    write_json(tmp_path / "run.json", {"limit": 100})
    write_json(tmp_path / "failure.json", {"message": "unit-test interrupted run"})
    write_jsonl(
        tmp_path / "summaries.jsonl",
        [
            {
                "task_success": True,
                "total_online_tokens": 100,
                "audit_tokens": 20,
            }
        ],
    )
    result = diagnose_run(tmp_path)
    assert result["completed_tasks"] == 1
    assert result["probability_fit"]["unique_raw_logits"] == 1
    assert sum(result["semantic_labels"].values()) == 2
    assert sum(result["operational_labels_not_semantic"].values()) == 1
    assert result["tokens_completed_tasks_including_audits"] == 120
    assert any("Constant" in w for w in result["warnings"])
