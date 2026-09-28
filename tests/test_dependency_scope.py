"""Software fixtures only; no experimental claims or generated research data."""

import json

import pytest

from veritas.cli import dispatch, parser
from veritas.dependency_scope import create_scope, screen_row
from veritas.io import file_hash, read_jsonl, write_json, write_jsonl
from veritas.schema import Task


def task(name="fixture", **changes):
    return Task(**{
        "task_id": name, "group_id": name, "source": "fixture",
        "source_revision": "a" * 40, "source_split": "train", "kind": "swe",
        "prompt": "Change return contract and update callers.", "official_holdout": False,
        "repo": "fixture/repo", "base_commit": "b" * 40,
        "private": {"patch": "SECRET_SOLUTION", "tests": "SECRET_TESTS"}, **changes,
    })


def prepared(path, tasks):
    write_jsonl(path / "tasks.jsonl", [t.model_dump(mode="json") for t in tasks])
    write_json(path / "splits.json", {t.group_id: {"split": "dev"} for t in tasks})
    write_json(path / "manifest.json", {
        "tasks_sha256": file_hash(path / "tasks.jsonl"),
        "splits_sha256": file_hash(path / "splits.json"),
    })
    return path


def test_public_only_and_hints_do_not_decide_eligibility():
    row = screen_row(task(), {"split": "dev", "secret": "SECRET_ASSIGNMENT"})
    assert row["screening_hints"]["caller"] == ["callers"]
    assert row["review"]["status"] == "pending"
    assert "SECRET" not in json.dumps(row)
    assert screen_row(task(prompt="Unclear issue"), {"split": "dev"}) is not None
    changed = task(private={"patch": "different secret"})
    assert screen_row(changed, {"split": "dev"}) == row


@pytest.mark.parametrize("split", ["test", "val", "calib", "backbone"])
def test_reserved_splits_never_screened(split):
    assert screen_row(task(), {"split": split}) is None


def test_holdout_and_non_swe_excluded():
    assert screen_row(task(official_holdout=True), {"split": "dev"}) is None
    assert screen_row(task(kind="math"), {"split": "dev"}) is None


def test_cli_reproducible_manifest_and_no_overwrite(tmp_path):
    data = prepared(tmp_path / "data", [
        task("z", prompt="No lexical match"), task("a"),
        task("holdout", official_holdout=True), task("math", kind="math"),
    ])
    first, second = tmp_path / "first", tmp_path / "second"
    args = parser().parse_args([
        "dependency-scope", "--tasks", str(data), "--output", str(first),
    ])
    manifest = dispatch(args)
    assert manifest == create_scope(data, second)
    assert manifest["queued_tasks"] == 2
    assert manifest["excluded_development_tasks"] == {"official_holdout": 1, "non_swe": 1}
    assert not manifest["cohort_finalized"] and not manifest["inference_started"]
    assert [r["task_id"] for r in read_jsonl(first / "review_queue.jsonl")] == ["a", "z"]
    for name, expected in manifest["artifact_hashes"].items():
        assert file_hash(first / name) == expected == file_hash(second / name)
        assert "SECRET" not in (first / name).read_text()
    with pytest.raises(ValueError, match="already exists"):
        create_scope(data, first)


def test_integrity_and_empty_source_fail_without_output(tmp_path):
    data = prepared(tmp_path / "data", [task()])
    output = tmp_path / "scope"
    with pytest.raises(ValueError, match="No non-holdout"):
        create_scope(data, output, source="missing")
    assert not output.exists()
    (data / "tasks.jsonl").write_text("tampered")
    with pytest.raises(ValueError, match="integrity"):
        create_scope(data, output)
    assert not output.exists()
