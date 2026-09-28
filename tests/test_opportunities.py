"""Software fixtures for verification opportunities; not benchmark evidence."""

import json
from pathlib import Path

from veritas.config import Config
from veritas.controller import Budget
from veritas.dependencies import extract_dependencies
from veritas.opportunities import OpportunityTracker
from veritas.runtime import run_task
from veritas.schema import Task, Usage, Verification
from veritas.store import EventStore


def source(root, path, text):
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text)


def fixture_repo(root):
    source(root, "api.py", "def f(value):\n    return value\n")
    source(root, "use.py", "from api import f\ndef caller():\n    return f(1)\n")


def test_opportunity_triggers_once_and_missing_trigger_finishes_explicitly(tmp_path):
    fixture_repo(tmp_path)
    tracker = OpportunityTracker(
        "api.py::f", "use.py::caller", extract_dependencies(tmp_path), final_fallback=True
    )
    source(tmp_path, "api.py", "def f(value, default=None):\n    return value\n")
    assert tracker.observe(extract_dependencies(tmp_path), 0, successful_edit=True)[0][
        "reason"
    ] == "target_signature_changed"
    source(
        tmp_path,
        "use.py",
        "from api import f\ndef caller():\n    value = f(1)\n    return value\n",
    )
    events = tracker.observe(extract_dependencies(tmp_path), 1, successful_edit=False)
    assert events == []
    source(
        tmp_path,
        "use.py",
        "from api import f\ndef caller():\n    return f(1, default=0)\n",
    )
    events = tracker.observe(extract_dependencies(tmp_path), 2, successful_edit=True)
    assert [event["name"] for event in events] == ["B"]
    assert tracker.observe(extract_dependencies(tmp_path), 3, successful_edit=True) == []
    report = tracker.finish("max_steps")
    assert report["events"]["A"]["status"] == "skipped"
    assert report["events"]["B"]["status"] == "skipped"
    assert report["events"]["A"]["decision_reason"] == "unhandled_at_termination:max_steps"


def test_pre_final_fallback_and_parse_error_diagnostic(tmp_path):
    fixture_repo(tmp_path)
    tracker = OpportunityTracker(
        "api.py::f", "use.py::caller", extract_dependencies(tmp_path), final_fallback=True
    )
    source(tmp_path, "api.py", "def f(value, default=None):\n    return value\n")
    tracker.observe(extract_dependencies(tmp_path), 0, successful_edit=True)
    events = tracker.observe(extract_dependencies(tmp_path), 1, before_final=True)
    assert events[0]["name"] == "B"
    assert events[0]["reason"] == "pre_final_fallback"

    fixture_repo(tmp_path)
    tracker = OpportunityTracker("api.py::f", "use.py::caller", extract_dependencies(tmp_path))
    source(tmp_path, "api.py", "def broken(:\n")
    assert tracker.observe(extract_dependencies(tmp_path), 0, successful_edit=True) == []
    assert tracker.report()["diagnostics"][0]["reason"] == "parse_error_or_missing_ambiguous_symbol"


def test_opportunity_handling_keeps_skips_budget_and_feedback_separate(tmp_path):
    fixture_repo(tmp_path)
    tracker = OpportunityTracker("api.py::f", "use.py::caller", extract_dependencies(tmp_path))
    source(tmp_path, "api.py", "def f(value, default=None):\n    return value\n")
    tracker.observe(extract_dependencies(tmp_path), 0, successful_edit=True)
    called = False

    def check(_event):
        nonlocal called
        called = True
        return Verification(verdict="FAIL", reason="caller broke", cost=0.02)

    budget = Budget(0.02)
    assert tracker.handle("A", "00", budget, 0.02, check) is None
    assert not called
    assert float(budget.spent) == 0.0
    assert tracker.report()["events"]["A"]["status"] == "skipped"

    fixture_repo(tmp_path)
    tracker = OpportunityTracker("api.py::f", "use.py::caller", extract_dependencies(tmp_path))
    source(tmp_path, "api.py", "def f(value, default=None):\n    return value\n")
    tracker.observe(extract_dependencies(tmp_path), 0, successful_edit=True)
    feedback = tracker.handle("A", "10", Budget(0.02), 0.02, check)
    assert "Post-edit review requests repair" in feedback
    assert tracker.report()["events"]["A"]["status"] == "checked"

    fixture_repo(tmp_path)
    tracker = OpportunityTracker("api.py::f", "use.py::caller", extract_dependencies(tmp_path))
    source(tmp_path, "api.py", "def f(value, default=None):\n    return value\n")
    tracker.observe(extract_dependencies(tmp_path), 0, successful_edit=True)
    assert tracker.handle("A", "10", Budget(0), 0.02, check) is None
    assert tracker.report()["events"]["A"]["status"] == "budget_blocked"


class StubPolicy:
    def __init__(self, proposals):
        self.proposals = iter(proposals)

    def propose(self, context):
        return json.dumps(next(self.proposals)), Usage(prompt_tokens=1, completion_tokens=1)


class StubSandbox:
    def __init__(self, workspace):
        self.workspace = Path(workspace)
        self.workspace.mkdir()
        fixture_repo(self.workspace)

    def execute(self, action):
        tool, args = action.proposal.tool, action.proposal.args
        if tool == "write_file":
            (self.workspace / args["path"]).write_text(args["content"])
        return {"exit_code": 0, "output": "ok"}


def swe_task():
    return Task(
        task_id="fixture-swe",
        group_id="fixture-swe",
        source="unit-test-only",
        source_revision="unit",
        source_split="train",
        kind="swe",
        prompt="Change f signature and update callers.",
        official_holdout=False,
        repo="fixture/repo",
        base_commit="a" * 40,
    )


def test_runtime_shadow_observer_records_without_checks_or_feedback(tmp_path):
    cfg = Config()
    cfg.run.allow_uncalibrated = True
    cfg.run.policy = "never"
    cfg.run.score_critic = False
    cfg.run.max_steps = 2
    cfg.opportunities.target_identity = "api.py::f"
    cfg.opportunities.caller_identity = "use.py::caller"
    cfg.opportunities.mode = "shadow"
    sandbox = StubSandbox(tmp_path / "work")
    policy = StubPolicy(
        [
            {
                "tool": "write_file",
                "args": {"path": "api.py", "content": "def f(value, default=None):\n    return value\n"},
            },
            {"tool": "final_answer", "args": {"answer": "done"}},
        ]
    )
    store = EventStore(tmp_path / "events.db")
    summary = run_task(
        swe_task(), {"split": "dev"}, cfg, policy, None, None, sandbox, store, tmp_path / "run"
    )
    opportunities = summary["opportunity_observation"]
    assert opportunities["mode"] == "shadow"
    assert opportunities["optional_checks_executed"] == 0
    assert opportunities["events"]["A"]["status"] == "skipped"
    assert opportunities["events"]["A"]["decision_reason"] == "shadow_observation_only"
    assert opportunities["events"]["B"]["reason"] == "pre_final_fallback"
    assert summary["verification_spent"] == 0
    store.close()
