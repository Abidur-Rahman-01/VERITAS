"""Software fixtures only. These tests are not empirical benchmark results."""

import json
from contextlib import closing
from types import SimpleNamespace

import pytest
from test_runtime import StubPolicy, StubSandbox, task

from veritas.config import Config, GraphConfig, SandboxConfig
from veritas.context import compact_context
from veritas.contracts import contract
from veritas.controller import Budget
from veritas.graph import DAG, Node
from veritas.graph_verifier import GraphVerifier
from veritas.models import ModelOutputError
from veritas.report import action_metrics
from veritas.runtime import run_task
from veritas.sanitize import sanitize
from veritas.schema import Proposal, Usage, Verification
from veritas.state import tree_hash
from veritas.store import EventStore


def action(tool, **args):
    return contract(Proposal(tool=tool, args=args))


class ReviewModel:
    def __init__(self, verdict="PASS", error=False):
        self.calls, self.verdict, self.error = [], verdict, error

    def verify(self, context, candidate, cost):
        self.calls.append((context, candidate))
        assert "####" not in context and "private" not in context
        usage = Usage(prompt_tokens=7, completion_tokens=3)
        if self.error:
            raise ModelOutputError("incomplete output", usage, "{")
        return Verification(
            verdict=self.verdict, reason="Recheck the result", usage=usage, cost=cost
        )


def verifier(model=None, **settings):
    return GraphVerifier(model, SandboxConfig(), [], GraphConfig(**settings))


def verify(engine, candidate, path, budget=None, **kwargs):
    return engine.verify_graph(
        "software fixture", candidate, 0.02, path, tree_hash(path), budget or Budget(0.04), **kwargs
    )


def test_dag_slices_shared_dependencies_and_schedules_ready_nodes():
    dag = DAG(
        [
            Node("root"),
            Node("cheap", ("root",), 1),
            Node("costly", ("root",), 10),
            Node("join", ("cheap", "costly")),
            Node("unused", (), 100),
        ]
    )
    assert dag.order(["join"]) == ["root", "cheap", "costly", "join"]
    assert dag.slice(["cheap"]) == {"root", "cheap"}
    assert dag.describe(["join"])["edges"] == [
        ["root", "cheap"],
        ["root", "costly"],
        ["cheap", "join"],
        ["costly", "join"],
    ]
    with pytest.raises(ValueError, match="Unknown target"):
        dag.order(["missing"])


@pytest.mark.parametrize(
    "nodes",
    [
        [Node("x"), Node("x")],
        [Node("x", ("missing",))],
        [Node("x", ("y",)), Node("y", ("x",))],
        [Node("good"), Node("unused", ("unused",))],
    ],
)
def test_dag_rejects_invalid_graphs(nodes):
    with pytest.raises(ValueError):
        DAG(nodes)


def test_deterministic_failure_stops_before_probes_and_model(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("value = 1\n")
    engine = verifier(ReviewModel())
    engine.probes = [["pytest", "test_a.py"]]
    monkeypatch.setattr(engine, "_probe", lambda *_: pytest.fail("unnecessary test execution"))
    verdict, trace = verify(
        engine, action("edit_file", path="a.py", old="missing", new="2"), tmp_path
    )
    assert verdict.verdict == "FAIL" and verdict.basis == "deterministic"
    assert verdict.certificate["matches"] == 0
    assert [r["node"] for r in trace["checks"]] == ["candidate"]
    assert engine.model.calls == [] and verdict.usage.total == verdict.cost == 0
    assert (tmp_path / "a.py").read_text() == "value = 1\n"


def test_cache_reuse_invalidates_when_workspace_changes(tmp_path):
    path = tmp_path / "a.py"
    path.write_text("value = 1\n")
    engine = verifier(cache_entries=2)
    candidate = action("edit_file", path="a.py", old="1", new="2")
    assert verify(engine, candidate, tmp_path)[0].verdict == "PASS"
    assert verify(engine, candidate, tmp_path)[1]["cache_hits"] == 2
    path.write_text("value = 3\n")
    verdict, trace = verify(engine, candidate, tmp_path)
    assert verdict.verdict == "FAIL" and trace["cache_hits"] == 0
    assert len(engine.cache) <= 2


def test_syntax_certificate_checks_resulting_file(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n")
    verdict, _ = verify(
        verifier(), action("edit_file", path="a.py", old="return 1", new="return ("), tmp_path
    )
    assert verdict.verdict == "FAIL" and verdict.certificate["check"] == "python_ast"
    assert verdict.certificate["line"] == 2


@pytest.mark.parametrize(
    "before,after,expected,calls",
    [
        (0, 1, "FAIL", 2),
        (1, 1, "PASS", 1),
        (0, 0, "PASS", 2),
        (2, 0, "ERROR", 1),
        (0, 5, "ERROR", 2),
    ],
)
def test_probe_graph_handles_existing_failures_and_infrastructure(
    tmp_path, monkeypatch, before, after, expected, calls
):
    (tmp_path / "a.py").write_text("x = 1\n")
    engine = verifier()
    engine.probes = [["pytest", "test_a.py"], ["pytest", "unused.py"]]
    observed = []

    def probe(workspace, argv, candidate=None):
        observed.append((argv, candidate))
        assert argv[-1] == "test_a.py"  # max_probes=1 backward-slices the second branch.
        return {"exit_code": before if candidate is None else after, "output": "fixture"}

    monkeypatch.setattr(engine, "_probe", probe)
    candidate = action("edit_file", path="a.py", old="1", new="2")
    verdict, trace = verify(engine, candidate, tmp_path)
    assert verdict.verdict == expected and len(observed) == calls
    assert "baseline:1" not in trace["schedule"]
    if expected == "FAIL":
        assert verdict.certificate["check"] == "configured_test_regression"
    verify(engine, candidate, tmp_path)
    assert len(observed) == calls * 2  # Stochastic tests are NEVER cached.


def test_probe_runs_isolated_clones_and_preserves_original(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x = 1\n")
    before = tree_hash(tmp_path)
    seen = []

    class ProbeSandbox:
        def __init__(self, workspace, config):
            self.workspace = workspace

        def execute(self, candidate):
            if candidate.proposal.tool == "edit_file":
                (self.workspace / "a.py").write_text("x = 2\n")
                return {"exit_code": 0, "output": "edited"}
            assert not (self.workspace / "test-side-effect").exists()
            (self.workspace / "test-side-effect").write_text("artifact")
            seen.append(self.workspace)
            return {
                "exit_code": int("2" in (self.workspace / "a.py").read_text()),
                "output": "pytest",
            }

    monkeypatch.setattr("veritas.graph_verifier.DockerSandbox", ProbeSandbox)
    engine = verifier()
    engine.probes = [["pytest", "test_a.py"]]
    verdict, _ = verify(engine, action("edit_file", path="a.py", old="1", new="2"), tmp_path)
    assert verdict.verdict == "FAIL" and len(set(seen)) == 2
    assert tree_hash(tmp_path) == before


def test_model_opinion_is_not_certificate_and_budget_is_reserved(tmp_path):
    engine, budget = verifier(ReviewModel("FAIL")), Budget(0.02)
    candidate = action("final_answer", answer="2")
    verdict, trace = verify(engine, candidate, tmp_path, budget)
    assert verdict.verdict == "REVIEW" and verdict.certificate is None
    assert verdict.basis == "model_opinion" and verdict.usage.total == 10
    assert float(budget.spent) == 0.02 and trace["semantic_calls"] == 1
    second, trace = verify(engine, candidate, tmp_path, budget)
    assert second.verdict == "PASS" and second.usage.total == 0
    assert len(engine.model.calls) == 1 and trace["checks"] == []


@pytest.mark.parametrize(
    "settings,budget,allowed",
    [
        ({"semantic_final_review": False}, 0.1, True),
        ({"max_semantic_calls": 0}, 0.1, True),
        ({}, 0, True),
        ({}, 0.1, False),
    ],
)
def test_disabled_review_never_loads_or_calls_a_model(tmp_path, settings, budget, allowed):
    verdict, trace = verify(
        verifier(None, **settings),
        action("final_answer", answer="2"),
        tmp_path,
        Budget(budget),
        allow_review=allowed,
    )
    assert verdict.verdict == "PASS" and verdict.usage.total == 0
    assert not trace["checks"]


def test_model_error_keeps_usage_and_charges_once(tmp_path):
    engine, budget = verifier(ReviewModel(error=True)), Budget(0.04)
    verdict, _ = verify(engine, action("final_answer", answer="2"), tmp_path, budget)
    assert verdict.verdict == "ERROR" and verdict.usage.total == 10
    assert float(budget.spent) == 0.02


def test_context_compacts_payloads_preserves_goal_and_does_not_mutate():
    t = task()
    t.prompt = "entire task " * 1000
    history = [
        {
            "action": {"tool": "write_file", "args": {"path": "a.py", "content": "x" * 10000}},
            "observation": sanitize("start " + "x" * 10000 + " end", "fixture"),
        }
    ]
    original = json.dumps(history)
    result = json.loads(compact_context(t, history, 2000, 200, 2))
    assert result["user_task"] == t.prompt
    entry = result["recent_history"][0]
    assert entry["action"]["args"]["content"]["omitted_chars"] == 10000
    assert entry["observation"]["content"].startswith("start")
    assert entry["observation"]["content"].endswith("end")
    assert len(entry["observation"]["content"]) <= 200
    assert original == json.dumps(history)


def graph_run(tmp_path, proposals, model, **run_settings):
    cfg = Config()
    cfg.run.policy, cfg.run.score_critic = "graph", False
    cfg.run.compact_history, cfg.run.max_replans, cfg.run.max_steps = True, 1, 4
    for key, value in run_settings.items():
        setattr(cfg.run, key, value)
    sandbox = StubSandbox(tmp_path / "work")
    with closing(EventStore(tmp_path / "events.db")) as store:
        summary = run_task(
            task(),
            {"split": "dev"},
            cfg,
            StubPolicy(proposals),
            None,
            GraphVerifier(model, cfg.sandbox, [], cfg.graph),
            sandbox,
            store,
            tmp_path / "run",
        )
        rows = [r.model_dump(mode="json") for r in store.records()]
    return summary, rows


def test_runtime_graph_one_review_one_revision_no_critic(tmp_path):
    model = ReviewModel("FAIL")
    summary, rows = graph_run(
        tmp_path,
        [
            {"tool": "final_answer", "args": {"answer": "3"}},
            {"tool": "final_answer", "args": {"answer": "2"}},
        ],
        model,
    )
    assert summary["task_success"] is True and summary["critic_tokens"] == 0
    assert summary["total_online_tokens"] == 40 and summary["verification_spent"] == 0.02
    assert summary["graph_model_calls"] == len(model.calls) == summary["replans"] == 1
    assert summary["replan_tokens"] == 15
    assert rows[0]["revision_requested"] and not rows[0]["executed"]
    assert rows[1]["executed"] and rows[1]["p_error"] is None
    metrics = action_metrics(rows)
    assert metrics["advisory_reviews"] == 1 and metrics["false_rejections"] == 0


def test_runtime_invalid_revision_falls_back_without_extra_loop(tmp_path):
    summary, rows = graph_run(
        tmp_path,
        [
            {"tool": "final_answer", "args": {"answer": "2"}},
            {"tool": "python", "args": {"code": "print(9)"}},
        ],
        ReviewModel("FAIL"),
    )
    assert summary["task_success"] is True
    assert summary["final_selection"] == "reviewed_original_fallback"
    assert summary["termination_reason"] == "replan_limit"
    assert rows[-1]["blocked"] and not rows[-1]["executed"]


def test_runtime_token_stop_and_final_fallback(tmp_path):
    summary, _ = graph_run(
        tmp_path,
        [{"tool": "final_answer", "args": {"answer": "2"}}],
        ReviewModel("FAIL"),
        max_online_tokens=20,
    )
    assert summary["task_success"] is True
    assert summary["total_online_tokens"] == 25  # Last iteration can overshoot the soft stop.
    assert summary["termination_reason"] == "online_token_stop"
    assert summary["final_selection"] == "reviewed_original_fallback"


def test_runtime_no_useless_review_on_last_allowed_step(tmp_path):
    model = ReviewModel("FAIL")
    summary, _ = graph_run(
        tmp_path, [{"tool": "final_answer", "args": {"answer": "2"}}], model, max_steps=1
    )
    assert summary["task_success"] is True and summary["verifier_tokens"] == 0
    assert model.calls == []


def test_runtime_graph_error_uses_original_answer_and_reports_failure(tmp_path):
    summary, rows = graph_run(
        tmp_path, [{"tool": "final_answer", "args": {"answer": "2"}}], ReviewModel(error=True)
    )
    assert summary["task_success"] is True and summary["total_online_tokens"] == 25
    assert action_metrics(rows)["verifier_errors"] == 1
    assert action_metrics(rows)["fallback_actions"] == 1


def test_trained_critic_group_leakage_is_blocked_before_inference(tmp_path):
    cfg = Config()
    cfg.run.allow_uncalibrated = True
    with pytest.raises(ValueError, match="critic training fit groups"):
        run_task(
            task(),
            {"split": "test"},
            cfg,
            None,
            SimpleNamespace(metadata={"fit_groups": [task().group_id]}),
            None,
            None,
            None,
            tmp_path,
        )


def test_blocked_failures_are_not_dropped_from_error_counts():
    metrics = action_metrics(
        [{"blocked": True, "critic_error": "unavailable", "fallback_reason": "budget"}]
    )
    assert metrics["critic_errors"] == metrics["fallback_actions"] == 1
