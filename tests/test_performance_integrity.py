"""Failure-path and comparison fixtures are software tests, not benchmark data."""

import json

import httpx
import pytest
from test_runtime import StubPolicy, StubSandbox, StubVerifier, task

from veritas.calibration import assess_calibration, fit_artifact, load_artifact
from veritas.config import Config, ModelConfig
from veritas.io import write_json, write_jsonl
from veritas.models import LocalModel, ModelOutputError, parse_probability
from veritas.replay import load_tuning, tune
from veritas.report import action_metrics, online_report
from veritas.runtime import run_task
from veritas.schema import Usage
from veritas.store import EventStore


@pytest.mark.parametrize("value", [None, True, 80, -0.1, "uncertain", "NaN", "120%"])
def test_bad_probability_is_never_silently_half(value):
    with pytest.raises((ValueError, TypeError)):
        parse_probability(json.dumps({"error_probability": value}))


def test_explicit_probability_percentage():
    assert parse_probability('{"error_probability":"0.5%"}') == 0.005
    assert parse_probability('{"error_probability":0.5}') == 0.5
    with pytest.raises(ValueError):
        parse_probability('{"risk":0.5}')


def test_truncation_preserves_usage():
    model = LocalModel(
        ModelConfig(),
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "{"}, "finish_reason": "length"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 7},
                },
            )
        ),
    )
    with pytest.raises(ModelOutputError) as error:
        model.propose("fixture")
    assert error.value.usage.total == 17 and error.value.usage.measured
    model.close()


class BrokenCritic:
    def score(self, *args):
        raise ModelOutputError(
            "Missing probability", Usage(prompt_tokens=5, completion_tokens=2), "{}"
        )


@pytest.mark.parametrize("budget,executed", [(0.02, True), (0, False)])
def test_missing_score_fallback_is_explicit_and_budgeted(tmp_path, budget, executed):
    cfg = Config()
    cfg.run.allow_uncalibrated = True
    cfg.run.verification_budget = budget
    sandbox = StubSandbox(tmp_path / "work")
    store = EventStore(tmp_path / "events.db")
    summary = run_task(
        task(),
        {"split": "dev"},
        cfg,
        StubPolicy([{"tool": "final_answer", "args": {"answer": "2"}}]),
        BrokenCritic(),
        StubVerifier(["PASS"]),
        sandbox,
        store,
        tmp_path / "run",
    )
    row = next(store.records())
    assert row.raw_logit is None and row.p_error is None and row.delta is None
    assert row.critic_error and row.fallback_reason and row.critic_raw_output == "{}"
    assert row.executed is executed
    assert row.blocked is not executed
    assert summary["critic_tokens"] == 7
    assert summary["verification_spent"] == budget
    store.close()


def test_online_baseline_copies_no_checkpoint_or_critic(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Online pre-execution verification needs no restore copy")

    monkeypatch.setattr("veritas.runtime.Checkpoint", forbidden)
    cfg = Config()
    cfg.run.allow_uncalibrated, cfg.run.score_critic, cfg.run.policy = True, False, "always"
    sandbox = StubSandbox(tmp_path / "work")
    store = EventStore(tmp_path / "events.db")
    summary = run_task(
        task(),
        {"split": "dev"},
        cfg,
        StubPolicy([{"tool": "final_answer", "args": {"answer": "2"}}]),
        None,
        StubVerifier(["PASS"]),
        sandbox,
        store,
        tmp_path / "run",
    )
    assert summary["critic_tokens"] == 0 and summary["total_online_tokens"] == 18
    assert next(store.records()).restored_hash is None
    store.close()


def artifact_fixture(tmp_path, step):
    rows = [step(i, split="calib", calibration_role="probability") for i in range(20)]
    rows += [step(i, split="calib", calibration_role="verifier_stats") for i in range(20, 40)]
    rows += [step(i, split="val") for i in range(40, 50)]
    path, artifact = tmp_path / "records.jsonl", tmp_path / "artifact.json"
    write_jsonl(path, rows)
    fit_artifact(path, artifact)
    return path, artifact


def test_manual_statistics_cannot_bypass_evidence(tmp_path, step):
    _, path = artifact_fixture(tmp_path, step)
    artifact = load_artifact(path)
    artifact["statistics"]["final_answer"]["false_positive_rate"] = 0.05
    write_json(path, artifact)
    with pytest.raises(ValueError, match="differs from its evidence"):
        load_artifact(path)


def test_threshold_edit_cannot_bypass_evidence(tmp_path, step):
    records, artifact = artifact_fixture(tmp_path, step)
    tuning_path = tmp_path / "tuning.json"
    tuning = tune(records, artifact, tuning_path, [0.02])
    assert load_tuning(tuning_path, artifact) == tuning
    tuning["thresholds"]["rcvov:0.02"] = 4321
    write_json(tuning_path, tuning)
    with pytest.raises(ValueError, match="Thresholds differ"):
        load_tuning(tuning_path, artifact)


def test_calibration_assessment_is_held_out(tmp_path, step):
    records, artifact = artifact_fixture(tmp_path, step)
    report = assess_calibration(records, artifact, tmp_path / "quality.json")
    assert report["auroc"] == 1 and report["task_groups"] == 10
    assert report["label_and_score_coverage"] == 1
    with pytest.raises(ValueError, match="overlaps"):
        assess_calibration(records, artifact, tmp_path / "invalid.json", "calib")


def test_unlabeled_rejection_is_unknown_not_zero(step):
    row = step(
        0,
        decision="verify",
        verification={"verdict": "FAIL", "reason": "fixture"},
        error_label=None,
    )
    metrics = action_metrics([row])
    assert metrics["false_rejections"] is None and metrics["errors_caught"] is None
    assert metrics["semantic_label_coverage"] == 0 and metrics["unlabeled_rejections"] == 1


def test_incomplete_online_success_is_not_a_full_score(tmp_path):
    path = tmp_path / "summaries.jsonl"
    write_jsonl(
        path,
        [
            {
                "task_success": score,
                "total_online_tokens": 10,
                "audit_tokens": 0,
                "token_usage_complete": True,
                "budget_violation": False,
            }
            for score in [True, None]
        ],
    )
    report = online_report(path, tmp_path / "report.json")
    assert report["task_success_rate"] is None
    assert report["scored_subset_success_rate"] == 1


def test_windows_harness_requires_real_environment(monkeypatch):
    from veritas.swe import require_supported_host

    monkeypatch.setattr("veritas.swe.sys.platform", "win32")
    with pytest.raises(ValueError, match="WSL2"):
        require_supported_host()


def test_targeted_edit_requires_exact_unambiguous_match():
    from veritas.contracts import contract
    from veritas.schema import Proposal
    from veritas.worker import replace_unique

    proposal = Proposal(
        tool="edit_file", args={"path": "a.py", "old": "value = 1", "new": "value = 2"}
    )
    assert contract(proposal).action_class == "code_edit"
    assert replace_unique("value = 1\n", "value = 1", "value = 2", "a.py") == "value = 2\n"
    for old in ["", "absent", "x"]:
        with pytest.raises(ValueError, match="exactly once"):
            replace_unique("xx", old, "z", "a.txt")
    with pytest.raises(SyntaxError):
        replace_unique("value = 1", "1", "(", "a.py")


@pytest.mark.parametrize("before,after,verdict", [(1, 1, "PASS"), (0, 1, "FAIL"), (0, 0, "PASS")])
def test_probe_rejects_new_failure_not_existing_failure(
    tmp_path, monkeypatch, before, after, verdict
):
    from veritas.config import SandboxConfig
    from veritas.contracts import contract
    from veritas.schema import Proposal, Verification
    from veritas.verifier import Verifier

    calls = []

    class Sandbox:
        def __init__(self, workspace, config):
            self.is_baseline = workspace.name == "baseline"

        def execute(self, action):
            if action.proposal.tool == "run_tests":
                return {"exit_code": before if self.is_baseline else after, "output": "fixture"}
            return {"exit_code": 0, "output": "edited"}

    class Model:
        def verify(self, context, action, cost):
            calls.append(context)
            return Verification(verdict="PASS", reason="fixture", cost=cost)

    monkeypatch.setattr("veritas.verifier.DockerSandbox", Sandbox)
    action = contract(Proposal(tool="write_file", args={"path": "a.py", "content": "x=1"}))
    result = Verifier(Model(), SandboxConfig(), [["pytest", "-q"]]).verify(
        "context", action, 0.02, tmp_path
    )
    assert result.verdict == verdict
    assert bool(calls) is (verdict == "PASS")
