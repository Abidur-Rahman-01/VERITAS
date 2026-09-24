"""Small software fixtures only; never benchmark observations."""

import json
from pathlib import Path

import httpx
import pytest
import yaml

from veritas.comparison import (
    ComparisonConfig,
    comparison_rows,
    create_plan,
    discover_models,
    grade_swe,
    read_plan,
    report_comparison,
    run_comparison,
)
from veritas.config import ModelConfig
from veritas.io import file_hash, write_json, write_jsonl
from veritas.schema import Task


def setup_plan(tmp_path, monkeypatch, limit=2, policies=None):
    data = tmp_path / "data"
    tasks = [
        Task(
            task_id=f"unit-{n}",
            group_id=f"unit-{n}",
            source="unit-fixture",
            source_revision="unit",
            source_split="train",
            kind="gsm8k",
            prompt=f"Software fixture {n}",
            official_holdout=False,
            private={"answer": "#### 2"},
        )
        for n in range(3)
    ]
    write_jsonl(data / "tasks.jsonl", (t.model_dump(mode="json") for t in tasks))
    write_json(data / "splits.json", {t.task_id: {"split": "dev"} for t in tasks})
    write_json(
        data / "manifest.json",
        {
            "tasks_sha256": file_hash(data / "tasks.jsonl"),
            "splits_sha256": file_hash(data / "splits.json"),
            "sources": {"unit-fixture": {}},
        },
    )
    base = tmp_path / "base.yaml"
    base.write_text("{}")
    config = tmp_path / "comparison.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "tasks": str(data),
                "base_config": str(base),
                "limit": limit,
                "policies": policies or ["never"],
            }
        )
    )
    monkeypatch.setattr(
        "veritas.comparison.discover_models",
        lambda *_: ([{"name": n, "digest": n} for n in ["a", "b"]], []),
    )
    output = tmp_path / "output"
    plan = create_plan(config, output)
    return output, plan


def test_discover_metadata_excludes_embeddings(monkeypatch):
    def respond(request):
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "chat", "digest": "abc"},
                        {"name": "embed", "digest": "def"},
                    ]
                },
            )
        assert request.url.path == "/api/show"  # No inference or pull requests.
        name = json.loads(request.content)["model"]
        return httpx.Response(
            200, json={"capabilities": ["completion" if name == "chat" else "embedding"]}
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        "veritas.comparison.httpx.Client",
        lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw),
    )
    selected, excluded = discover_models(ModelConfig(backend="ollama", base_url="http://unit"))
    assert [r["name"] for r in selected] == ["chat"]
    assert excluded[0]["name"] == "embed"
    with pytest.raises(ValueError, match="not installed"):
        discover_models(ModelConfig(backend="ollama", base_url="http://unit"), ["missing"])


def test_plan_is_paired_and_tamper_detected(tmp_path, monkeypatch):
    output, plan = setup_plan(tmp_path, monkeypatch)
    assert plan["jobs"] == 4
    assert plan["base_config"]["run"]["score_critic"] is False
    assert plan["base_config"]["run"]["audit_all"] is False
    assert plan["holdout_tasks"] == 0
    assert read_plan(output) == plan
    plan["jobs"] = 99
    write_json(output / "plan.json", plan)
    with pytest.raises(ValueError, match="plan changed"):
        read_plan(output)


def test_failure_resume_and_missing_scores(tmp_path, monkeypatch):
    output, plan = setup_plan(tmp_path, monkeypatch)
    calls = []
    fail = [True]

    def fake_collect(tasks_dir, config, destination, **kwargs):
        task, _ = kwargs["selected_tasks"][0]
        calls.append((config.model.name, task.task_id))
        if config.model.name == "b" and fail[0]:
            raise TimeoutError("software test failure")
        write_jsonl(
            Path(destination) / "summaries.jsonl",
            [
                {
                    "task_success": True,
                    "total_online_tokens": 20,
                    "audit_tokens": 0,
                    "token_usage_complete": True,
                }
            ],
        )

    monkeypatch.setattr("veritas.runtime.collect", fake_collect)
    rows = run_comparison(output)
    assert len(calls) == 4
    assert rows[0]["success_rate"] == 1
    assert rows[1]["success_rate"] is None
    assert rows[1]["errors"] == 2
    run_comparison(output)
    assert len(calls) == 4  # Neither successes nor failed attempts retried implicitly.
    fail[0] = False
    rows = run_comparison(output, retry_failed=True)
    assert len(calls) == 6
    assert rows[1]["success_rate"] == 1
    assert rows[1]["has_retries"]
    report_comparison(output)
    assert (output / "comparison.csv").exists()
    assert len(comparison_rows(output, plan)) == 2


def test_swe_nonempty_patch_is_not_success_without_report(tmp_path, monkeypatch):
    from veritas.comparison import SWEOptions

    task = Task(
        task_id="swe:unit",
        group_id="swe:unit",
        source="fixture",
        source_revision="unit",
        source_split="test",
        kind="swe",
        prompt="Software fixture",
        official_holdout=True,
        private={"instance_id": "unit"},
    )
    write_jsonl(
        tmp_path / "predictions.jsonl",
        [
            {
                "instance_id": "unit",
                "model_patch": "diff --git fixture",
                "model_name_or_path": "model:tag",
            }
        ],
    )
    monkeypatch.setattr("veritas.comparison.subprocess.run", lambda *a, **kw: None)
    with pytest.raises(ValueError, match="report missing"):
        grade_swe(task, tmp_path, SWEOptions())
    write_json(tmp_path / "grading" / "comparison.grade.json", {"resolved_ids": ["unit"]})
    assert grade_swe(task, tmp_path, SWEOptions())[0] is True


def test_config_rejects_unknown_fields():
    with pytest.raises(ValueError):
        ComparisonConfig.model_validate({"made_up_setting": True})


def test_policies_share_tasks_and_keep_distinct_attempts(tmp_path, monkeypatch):
    output, plan = setup_plan(tmp_path, monkeypatch, policies=["never", "always"])
    calls = []

    def fake_collect(tasks_dir, config, destination, **kwargs):
        task, _ = kwargs["selected_tasks"][0]
        calls.append((config.model.name, config.run.policy, task.task_id))
        assert config.run.score_critic is False
        assert config.run.verification_budget == 0.2
        assert kwargs["artifact"] is None
        write_jsonl(
            Path(destination) / "summaries.jsonl",
            [
                {
                    "task_success": True,
                    "total_online_tokens": 20,
                    "audit_tokens": 0,
                    "token_usage_complete": True,
                }
            ],
        )

    monkeypatch.setattr("veritas.runtime.collect", fake_collect)
    rows = run_comparison(output)
    assert plan["jobs"] == len(calls) == 8
    assert len(rows) == 4
    assert all(row["success_rate"] == 1 for row in rows)
    for model in ["a", "b"]:
        assert {task for m, p, task in calls if m == model and p == "always"} == {
            task for m, p, task in calls if m == model and p == "never"
        }
    run_comparison(output)
    assert len(calls) == 8


def test_scored_comparison_refuses_missing_calibration(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="need empirical calibration"):
        setup_plan(tmp_path, monkeypatch, policies=["never", "rcvov"])


def test_complete_scored_comparison_joins_tuning_and_uncertainty(tmp_path, monkeypatch, step):
    from veritas.calibration import fit_artifact
    from veritas.config import Config
    from veritas.provenance import critic_identity, verifier_identity
    from veritas.replay import tune

    setup_plan(tmp_path, monkeypatch)
    cfg = Config()
    identifiers = {"critic_id": critic_identity(cfg), "verifier_id": verifier_identity(cfg)}
    records = [
        step(i, split="calib", calibration_role=role, **identifiers)
        for role, offset in [("probability", 0), ("verifier_stats", 20)]
        for i in range(offset, offset + 20)
    ]
    records += [step(i, split="val", **identifiers) for i in range(40, 50)]
    records_path, artifact_path, tuning_path = (
        tmp_path / "records.jsonl",
        tmp_path / "calib.json",
        tmp_path / "tune.json",
    )
    write_jsonl(records_path, records)
    fit_artifact(records_path, artifact_path)
    tune(records_path, artifact_path, tuning_path, [0.2])
    spec_path = tmp_path / "comparison.yaml"
    spec = yaml.safe_load(spec_path.read_text())
    spec.update(
        policies=["never", "always", "error_impact", "rcvov"],
        calibration={"unit-fixture": {"artifact": str(artifact_path), "tuning": str(tuning_path)}},
    )
    spec_path.write_text(yaml.safe_dump(spec))
    output = tmp_path / "scored-output"
    create_plan(spec_path, output)

    def fake_collect(tasks_dir, config, destination, **kwargs):
        assert bool(kwargs["artifact"]) == (config.run.policy in {"rcvov", "error_impact"})
        assert config.run.dynamic_lambda == 0
        write_jsonl(
            Path(destination) / "summaries.jsonl",
            [
                {
                    "task_success": True,
                    "total_online_tokens": 20,
                    "audit_tokens": 0,
                    "token_usage_complete": True,
                }
            ],
        )

    monkeypatch.setattr("veritas.runtime.collect", fake_collect)
    rows = run_comparison(output)
    assert len(rows) == 8
    effects = json.loads((output / "policy_effects.json").read_text())
    assert len(effects) == 6 and all(r["complete"] for r in effects)
    assert all(r["success_delta"]["mean_difference_per_task"] == 0 for r in effects)
    # A calibration change must invalidate a frozen plan even when its plan hash remains intact.
    with artifact_path.open("a") as file:
        file.write(" ")
    with pytest.raises(ValueError, match="changed since planning"):
        read_plan(output)
