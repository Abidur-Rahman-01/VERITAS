"""Validation fixtures only, never reviewer evidence for real research tasks."""

import copy
import json

import pytest
from test_dependency_scope import prepared, task

from veritas.cli import dispatch, parser
from veritas.dependency_cohort import (
    Annotation,
    Evidence,
    Protocol,
    finalize_cohort,
    prepare_reviews,
    verify_cohort,
)
from veritas.dependency_scope import create_scope
from veritas.io import file_hash, read_jsonl, write_json, write_jsonl


def evidence(path="api.py"):
    return {"kind": "base_code", "quote": "def interface():", "path": path,
            "start_line": 1, "end_line": 2, "base_commit": "b" * 40,
            "file_sha256": "c" * 64}


def review(person, status="include"):
    return {"reviewer": person, "status": status, "reason": "Fixture evidence",
            "public_evidence": [{"kind": "issue", "quote": "return contract"}],
            "target_symbol": "interface", "target_evidence": evidence(),
            "caller_symbol": "caller", "caller_evidence": evidence("caller.py"),
            "independent_and_outcome_blind": True}


@pytest.fixture
def inputs(tmp_path):
    data = prepared(tmp_path / "data", [task("a"), task("b"), task("c")])
    scope = tmp_path / "scope"
    create_scope(data, scope)
    directory = tmp_path / "review"
    prepare_reviews(scope, directory)
    annotations = list(read_jsonl(directory / "annotations.jsonl"))
    for row in annotations:
        row["reviews"] = [review("reviewer-one"), review("reviewer-two")]
    annotations[-1]["reviews"] = [review("one", "uncertain"), review("two", "uncertain")]
    write_jsonl(directory / "annotations.jsonl", annotations)
    spec = json.loads(open("configs/dependency-protocol.example.json").read())
    spec.update(actor_identity="fixture frozen actor", verifier_identity="fixture verifier",
                trigger_a="first interface edit", trigger_b="first caller edit",
                feedback_and_repair="single rejection feedback followed by actor repair",
                grading_protocol="upstream independent SWE grading", meaningful_effect=0.1,
                outcome_blind_freeze=True)
    write_json(tmp_path / "protocol.json", spec)
    return dict(scope=scope, tasks=data, reviews=directory / "annotations.jsonl",
                protocol=tmp_path / "protocol.json", config="configs/experiment.yaml",
                output=tmp_path / "cohort")


def test_finalize_freezes_cohort_and_preserves_uncertain(inputs):
    result = finalize_cohort(**inputs)
    assert result["included_tasks"] == 2
    assert result["decisions"] == {"include": 2, "uncertain": 1}
    assert result["partitions"] == {"discovery": 1, "confirmation": 1}
    assert not result["execution_supported"]
    assert len(list(read_jsonl(inputs["output"] / "reviews.jsonl"))) == 3
    for name, expected in result["artifact_hashes"].items():
        assert file_hash(inputs["output"] / name) == expected
        assert "SECRET" not in (inputs["output"] / name).read_text()
    with pytest.raises(ValueError, match="already exists"):
        finalize_cohort(**inputs)
    other = {**inputs, "output": inputs["output"].with_name("repeat")}
    assert finalize_cohort(**other) == result


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "identity", "pending", "quote", "commit"])
def test_bad_annotations_do_not_create_cohort(inputs, mutation):
    rows = list(read_jsonl(inputs["reviews"]))
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows.append(rows[0])
    elif mutation == "identity":
        rows[0]["group_id"] = "different"
    elif mutation == "pending":
        rows[0]["reviews"] = []
    elif mutation == "quote":
        rows[0]["reviews"][0]["public_evidence"][0]["quote"] = "INVENTED"
    else:
        rows[0]["reviews"][0]["target_evidence"]["base_commit"] = "wrong"
    write_jsonl(inputs["reviews"], rows)
    with pytest.raises(ValueError):
        finalize_cohort(**inputs)
    assert not inputs["output"].exists()


def test_disagreement_and_distinct_reviewers(inputs):
    row = next(read_jsonl(inputs["reviews"]))
    row["reviews"][1]["status"] = "exclude"
    with pytest.raises(ValueError, match="adjudication"):
        Annotation.model_validate(row)
    row["adjudication"] = review("third")
    assert Annotation.model_validate(row).resolved.status == "include"
    row["adjudication"]["reviewer"] = "Reviewer-One"
    with pytest.raises(ValueError, match="distinct"):
        Annotation.model_validate(row)


def test_target_disagreement_requires_adjudication(inputs):
    row = next(read_jsonl(inputs["reviews"]))
    row["reviews"][1]["target_symbol"] = "other"
    with pytest.raises(ValueError, match="disagreement"):
        Annotation.model_validate(row)


@pytest.mark.parametrize("path", ["../api.py", "/api.py", "C:\\api.py", "api.txt"])
def test_code_evidence_path_boundary(path):
    with pytest.raises(ValueError):
        Evidence.model_validate(evidence(path))


def test_config_mismatch_and_scope_tampering(inputs):
    spec = json.loads(inputs["protocol"].read_text())
    spec["max_steps"] += 1
    write_json(inputs["protocol"], spec)
    with pytest.raises(ValueError, match="mismatch"):
        finalize_cohort(**inputs)
    (inputs["scope"] / "review_queue.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="integrity"):
        finalize_cohort(**inputs)
    assert not inputs["output"].exists()


def test_protocol_rejects_draft_and_duplicate_seeds(inputs):
    with pytest.raises(ValueError):
        Protocol.model_validate(json.loads(open("configs/dependency-protocol.example.json").read()))
    spec = json.loads(inputs["protocol"].read_text())
    spec["seeds"] = [41, 41, 41]
    with pytest.raises(ValueError, match="distinct seed"):
        Protocol.model_validate(spec)


def test_confirmation_partition_requires_distinct_units(inputs):
    spec = json.loads(inputs["protocol"].read_text())
    spec["partition_unit"] = "repository"
    write_json(inputs["protocol"], spec)
    with pytest.raises(ValueError, match="two partition units"):
        finalize_cohort(**inputs)


def test_prepare_cli_leaves_real_reviews_pending(inputs, tmp_path):
    directory = tmp_path / "new-review"
    args = parser().parse_args(["dependency-cohort", "prepare", "--scope", str(inputs["scope"]),
                               "--output", str(directory)])
    assert dispatch(args)["status"] == "unreviewed_template"
    assert all(r["reviews"] == [] for r in read_jsonl(directory / "annotations.jsonl"))
    with pytest.raises(FileExistsError):
        dispatch(args)


def test_missing_include_evidence(inputs):
    row = copy.deepcopy(next(read_jsonl(inputs["reviews"])))
    row["reviews"][0]["caller_evidence"] = None
    with pytest.raises(ValueError, match="base-code evidence"):
        Annotation.model_validate(row)


def test_frozen_cohort_verification_detects_mutation(inputs):
    finalize_cohort(**inputs)
    assert verify_cohort(inputs["output"])["status"] == "local_integrity_verified"
    (inputs["output"] / "protocol.json").write_text("{}")
    with pytest.raises(ValueError, match="integrity"):
        verify_cohort(inputs["output"])
