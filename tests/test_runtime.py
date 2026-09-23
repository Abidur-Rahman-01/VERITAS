import json
from pathlib import Path

from veritas.config import Config
from veritas.runtime import run_task
from veritas.schema import Task, Usage, Verification
from veritas.state import tree_hash
from veritas.store import EventStore


class StubPolicy:
    def __init__(self, proposals):
        self.proposals = iter(proposals)

    def propose(self, context):
        assert "private" not in context and "####" not in context
        return json.dumps(next(self.proposals)), Usage(prompt_tokens=10, completion_tokens=5)


class StubCritic:
    def score(self, context, action):
        return 2.0, Usage(prompt_tokens=3, completion_tokens=2)


class StubVerifier:
    def __init__(self, verdicts):
        self.verdicts = iter(verdicts)

    def verify(self, context, action, cost, workspace):
        return Verification(
            verdict=next(self.verdicts),
            reason="test diagnostic",
            cost=cost,
            usage=Usage(prompt_tokens=2, completion_tokens=1),
        )


class StubSandbox:
    def __init__(self, workspace):
        self.workspace = Path(workspace)
        self.workspace.mkdir()

    def execute(self, action):
        if action.proposal.tool == "write_file":
            (self.workspace / action.proposal.args["path"]).write_text(
                action.proposal.args["content"]
            )
        return {"exit_code": 0, "output": "operation completed"}


def task():
    return Task(
        task_id="unit",
        group_id="unit",
        source="unit-test-only",
        source_revision="unit",
        source_split="train",
        kind="gsm8k",
        prompt="A unit test arithmetic task",
        official_holdout=False,
        private={"answer": "#### 2"},
    )


def test_collection_full_record_and_restore(tmp_path):
    cfg = Config()
    cfg.run.allow_uncalibrated, cfg.run.audit_all, cfg.run.policy = True, True, "never"
    cfg.run.max_steps = 3
    sandbox = StubSandbox(tmp_path / "work")
    policy = StubPolicy(
        [
            {"tool": "write_file", "args": {"path": "a.txt", "content": "real mutation"}},
            {"tool": "final_answer", "args": {"answer": "2"}},
        ]
    )
    store = EventStore(tmp_path / "events.db")
    summary = run_task(
        task(),
        {"split": "calib", "calibration_role": "probability"},
        cfg,
        policy,
        StubCritic(),
        StubVerifier(["PASS", "PASS"]),
        sandbox,
        store,
        tmp_path / "run",
    )
    records = list(store.records())
    assert summary["task_success"] is True
    assert summary["total_online_tokens"] == 40
    assert summary["audit_tokens"] == 6
    assert summary["verification_spent"] == 0
    assert records[0].error_label is None  # A successful write is not semantic ground truth.
    assert records[0].restored_hash == records[0].state_before
    assert records[0].state_after != records[0].state_before
    assert (sandbox.workspace / "a.txt").read_text() == "real mutation"
    assert records[1].error_label == 0
    store.close()


def test_failed_verification_replans_and_charges(tmp_path):
    cfg = Config()
    cfg.run.allow_uncalibrated, cfg.run.policy, cfg.run.max_steps = True, "always", 2
    cfg.run.verification_budget = 0.04
    sandbox = StubSandbox(tmp_path / "work")
    initial = tree_hash(sandbox.workspace)
    policy = StubPolicy(
        [
            {"tool": "write_file", "args": {"path": "bad", "content": "bad"}},
            {"tool": "final_answer", "args": {"answer": "2"}},
        ]
    )
    store = EventStore(tmp_path / "events.db")
    summary = run_task(
        task(),
        {"split": "test"},
        cfg,
        policy,
        StubCritic(),
        StubVerifier(["FAIL", "PASS"]),
        sandbox,
        store,
        tmp_path / "run",
    )
    records = list(store.records())
    assert not records[0].executed
    assert records[0].restored_hash == initial
    assert not (sandbox.workspace / "bad").exists()
    assert summary["verification_spent"] == 0.04
    assert summary["replan_tokens"] == 15
    store.close()


def test_floor_blocks_before_critic(tmp_path):
    cfg = Config()
    cfg.run.allow_uncalibrated, cfg.run.max_steps = True, 1
    sandbox = StubSandbox(tmp_path / "work")
    store = EventStore(tmp_path / "events.db")
    policy = StubPolicy([{"tool": "read_file", "args": {"path": "../secret"}}])
    summary = run_task(
        task(), {"split": "dev"}, cfg, policy, None, None, sandbox, store, tmp_path / "run"
    )
    assert list(store.records())[0].blocked
    assert summary["critic_tokens"] == 0
    assert summary["policy_tokens"] == 15  # zero-token floor does not mean zero-token replan.
    store.close()
