"""Software-test fixtures, not experimental observations."""

import json

import pytest

from veritas.io import read_jsonl, write_jsonl
from veritas.labels import annotate_math_queue, apply_annotations
from veritas.schema import Task


def test_python_stdout_and_exit_are_not_semantic_labels(tmp_path, monkeypatch):
    task = Task(
        task_id="fixture",
        group_id="fixture",
        source="unit-fixture",
        source_revision="unit",
        source_split="train",
        kind="gsm8k",
        prompt="Software fixture",
        official_holdout=False,
        private={"answer": "#### 20"},
    )
    monkeypatch.setattr("veritas.data.load_tasks", lambda _: [(task, {"split": "dev"})])
    queue = []
    # Includes an intermediate number, a matching final number, successful text, runtime failure,
    # and missing observation data: none establishes semantic action correctness automatically.
    for i, observation in enumerate(
        [
            {"exit_code": 0, "output": "10"},
            {"exit_code": 0, "output": "20"},
            {"exit_code": 0, "output": "ok"},
            {"exit_code": 1, "output": "error"},
            {},
        ]
    ):
        queue.append(
            {
                "event_id": str(i),
                "task_id": "fixture",
                "action": {"proposal": {"tool": "python", "args": {"code": "print(10)"}}},
                "observation": {"content": json.dumps(observation)},
                "error_label": 0,
                "label_scope": "semantic",
                "label_source": "old_unsound_label",
            }
        )
    queue.append(
        {
            "event_id": "final",
            "task_id": "fixture",
            "action": {"proposal": {"tool": "final_answer", "args": {"answer": "20"}}},
        }
    )
    write_jsonl(tmp_path / "queue.jsonl", queue)
    result = annotate_math_queue(tmp_path / "queue.jsonl", "unused", tmp_path / "safe.jsonl")
    rows = list(read_jsonl(tmp_path / "safe.jsonl"))
    assert result == {"total": 6, "semantic_labeled": 1, "needs_review": 5}
    assert all(r["error_label"] is None and r["label_scope"] == "unknown" for r in rows[:-1])
    assert rows[-1]["error_label"] == 0
    with pytest.raises(ValueError, match="output exists"):
        annotate_math_queue(tmp_path / "queue.jsonl", "unused", tmp_path / "safe.jsonl")


def test_math_equivalence_and_unknown_tasks_not_mislabeled(tmp_path, monkeypatch):
    task = Task(
        task_id="fixture",
        group_id="fixture",
        source="unit-fixture",
        source_revision="unit",
        source_split="test",
        kind="math",
        prompt="Software fixture",
        official_holdout=True,
        private={"answer": "1/2"},
    )
    monkeypatch.setattr("veritas.data.load_tasks", lambda _: [(task, {"split": "test"})])
    row = {
        "event_id": "final",
        "task_id": "fixture",
        "action": {"proposal": {"tool": "final_answer", "args": {"answer": "0.5"}}},
    }
    write_jsonl(tmp_path / "queue.jsonl", [row])
    annotate_math_queue(tmp_path / "queue.jsonl", "unused", tmp_path / "safe.jsonl")
    assert next(read_jsonl(tmp_path / "safe.jsonl"))["error_label"] is None
    row["task_id"] = "missing"
    write_jsonl(tmp_path / "queue.jsonl", [row])
    with pytest.raises(ValueError, match="missing from prepared"):
        annotate_math_queue(tmp_path / "queue.jsonl", "unused", tmp_path / "invalid.jsonl")
    assert not (tmp_path / "invalid.jsonl").exists()


def test_null_review_does_not_erase_existing_labels(tmp_path, step):
    # Therefore recovery instructions must apply annotations to RAW exports, not polluted labels.
    row = step()
    write_jsonl(tmp_path / "raw.jsonl", [row])
    write_jsonl(
        tmp_path / "annotations.jsonl", [{"event_id": row["event_id"], "error_label": None}]
    )
    apply_annotations(
        tmp_path / "raw.jsonl", tmp_path / "annotations.jsonl", tmp_path / "out.jsonl"
    )
    assert next(read_jsonl(tmp_path / "out.jsonl"))["error_label"] == row["error_label"]
