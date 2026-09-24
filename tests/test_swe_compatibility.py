import pytest

from veritas.io import write_jsonl
from veritas.swe import evaluation_command


def test_grading_command_preserves_paths_and_local_namespace(tmp_path):
    path = tmp_path / "predictions with spaces.jsonl"
    write_jsonl(
        path, [{"instance_id": "unit__fixture-1", "model_patch": "", "model_name_or_path": "local"}]
    )
    argv = evaluation_command("task file.jsonl", path, "test-run", namespace="")
    assert str(path) in argv
    assert argv[-2:] == ["--namespace", "none"]


def test_invalid_prediction_refused(tmp_path):
    path = tmp_path / "bad.jsonl"
    write_jsonl(path, [{"instance_id": "unit__fixture-1"}])
    with pytest.raises(ValueError):
        evaluation_command("tasks.jsonl", path, "run")
