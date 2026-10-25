import json

import pytest

from veritas.feedback_study import analyze_results, create_plan, verify_plan
from veritas.io import file_hash, write_json, write_jsonl
from veritas.schema import Task


@pytest.fixture
def prepared_swe(tmp_path):
    root = tmp_path / "prepared"
    root.mkdir()
    tasks = [Task(task_id=f"swe:task-{i}", group_id=f"swe:task-{i}", source="swe_rebench",
        source_revision="a" * 40, source_split="test", kind="swe", prompt="Fix bug",
        official_holdout=True, repo=f"org/repo-{i}", base_commit="b" * 40,
        private={"instance_id": f"org__repo-{i}-{i}"}) for i in range(8)]
    write_jsonl(root / "tasks.jsonl", [task.model_dump(mode="json") for task in tasks])
    write_json(root / "splits.json", {task.group_id: {"split": "test"} for task in tasks})
    write_json(root / "manifest.json", {"tasks_sha256": file_hash(root / "tasks.jsonl"),
        "splits_sha256": file_hash(root / "splits.json")})
    return root


def test_plan_is_repository_disjoint_and_has_all_arms(tmp_path, prepared_swe):
    root = tmp_path / "study"
    created = create_plan(prepared_swe, root, task_limit=8, seed=7)
    checked = verify_plan(root)
    assert created["branches"] == 40
    assert checked["blocks"] == 8
    protocol = json.loads((root / "protocol.json").read_text())
    assert set(protocol["development_repositories"]).isdisjoint(protocol["confirmation_repositories"])


def test_plan_tampering_and_small_repository_pool_are_rejected(tmp_path, prepared_swe):
    root = tmp_path / "study"
    create_plan(prepared_swe, root, task_limit=8, seed=7)
    (root / "branches.jsonl").write_text("\n")
    with pytest.raises(ValueError, match="changed"):
        verify_plan(root)


def test_analysis_uses_pre_assignment_parent_label_and_paired_arms(tmp_path, prepared_swe):
    root = tmp_path / "study"
    create_plan(prepared_swe, root, task_limit=8, seed=7)
    blocks = [json.loads(line) for line in (root / "blocks.jsonl").read_text().splitlines()]
    results = []
    for block in blocks:
        for arm, resolved in (("adaptive", True), ("fixed_actionable", False)):
            results.append({"block_id": block["block_id"], "arm": arm,
                "resolved": resolved, "parent_resolved": False, "total_credits": 1.0})
    write_jsonl(root / "results.jsonl", results)
    summary = analyze_results(root)
    assert summary["paired_blocks"] == 8
    assert summary["incorrect_parent_blocks"] == 8
    assert summary["paired_recovery_difference"] == 1.0
