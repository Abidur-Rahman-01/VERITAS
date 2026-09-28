"""Software fixtures only; no benchmark claims."""
import json
from pathlib import Path

import pytest
import yaml
from test_comparison import setup_plan

from veritas.io import write_jsonl
from veritas.suite import SuiteConfig, create_suite, read_suite, run_suite, variants


def test_grid_validation():
    for grid in [{"run.policy": ["never"]}, {"model.max_tokens": []},
                 {"model.max_tokens": [1, 1]}, {"unknown.value": [1]}]:
        with pytest.raises(ValueError):
            variants(SuiteConfig(comparison={}, grid=grid))
    with pytest.raises(ValueError, match="max_variants"):
        variants(SuiteConfig(comparison={}, grid={"model.max_tokens": [1, 2]}, max_variants=1))


def test_suite_runtime_parameters_resume_and_plots(tmp_path, monkeypatch):
    setup_plan(tmp_path, monkeypatch)
    from veritas import comparison as comparison_module

    monkeypatch.setattr("veritas.suite.discover_models", comparison_module.discover_models)
    comparison = yaml.safe_load((tmp_path / "comparison.yaml").read_text())
    config = tmp_path / "suite.yaml"
    config.write_text(yaml.safe_dump({
        "comparison": comparison,
        "grid": {"model.max_tokens": [32, 64], "run.max_steps": [3]},
    }))
    output = tmp_path / "suite"
    manifest = create_suite(config, output)
    assert len(manifest["variants"]) == 2
    calls = []

    def collect(tasks, config, destination, **kwargs):
        calls.append((config.model.max_tokens, config.run.max_steps))
        write_jsonl(Path(destination) / "summaries.jsonl", [{
            "task_success": True, "total_online_tokens": 20, "policy_tokens": 20,
            "audit_tokens": 0, "token_usage_complete": True,
        }])

    monkeypatch.setattr("veritas.runtime.collect", collect)
    rows = run_suite(output)
    assert set(calls) == {(32, 3), (64, 3)}
    assert len(calls) == 8
    assert all(r["tokens_per_task"] == 20 for r in rows)
    assert all(r["known_policy_tokens"] == 40 for r in rows)
    assert list((output / "plots").glob("*.png"))
    assert list((output / "plots").glob("*.svg"))
    assert (output / "suite-results.csv").exists()
    run_suite(output)
    assert len(calls) == 8
    manifest["variants"].pop()
    (output / "suite.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="manifest changed"):
        read_suite(output)
