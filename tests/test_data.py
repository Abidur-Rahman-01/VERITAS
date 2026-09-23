import json

import yaml

from veritas.data import load_tasks, prepare
from veritas.io import file_hash, write_json, write_jsonl


def test_duplicate_tasks_keep_official_holdout(tmp_path):
    # Minimal software-test records, not a released or generated experiment dataset.
    source = {
        "repo": "unit/fixture",
        "revision": "a" * 40,
        "split": "train",
        "adapter": "swe",
        "expected_rows": 1,
        "official_holdout": False,
    }
    holdout = {**source, "split": "test", "official_holdout": True}
    manifest = tmp_path / "datasets.yaml"
    manifest.write_text(yaml.safe_dump({"sources": {"train": source, "test": holdout}}))
    row = {
        "instance_id": "test-1",
        "repo": "unit/fixture",
        "base_commit": "b" * 40,
        "problem_statement": "Unit test input",
        "patch": "private solution",
    }
    for name, spec in [("train", source), ("test", holdout)]:
        path = tmp_path / f"{name}.jsonl"
        write_jsonl(path, [row])
        write_json(path.with_suffix(".manifest.json"), {"spec": spec, "sha256": file_hash(path)})
    result = prepare(manifest, tmp_path, tmp_path / "prepared")
    assert result["unique_tasks"] == 1
    assert result["counts"] == {"test": 1}
    tasks = list(load_tasks(tmp_path / "prepared"))
    assert tasks[0][0].official_holdout
    assert tasks[0][0].private["patch"] == "private solution"
    mapping = json.loads((tmp_path / "prepared/splits.json").read_text())
    assert mapping["swe:test-1"]["split"] == "test"
