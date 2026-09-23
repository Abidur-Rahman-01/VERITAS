"""Small deterministic software-test fixtures, never used as experimental datasets."""

import pytest

from veritas.contracts import contract
from veritas.schema import Proposal, StepRecord, Verification


@pytest.fixture
def step():
    def make(index=0, **updates):
        action = contract(Proposal(tool="final_answer", args={"answer": "2"}))
        values = dict(
            event_id=f"event-{index}",
            task_id=f"task-{index}",
            group_id=f"task-{index}",
            source="unit-test-only",
            run_id="run",
            model="stub",
            step_id=index,
            split="test",
            context="A unit-test context",
            action=action,
            raw_logit=2.0 if index % 2 else -2.0,
            p_error=0.8 if index % 2 else 0.2,
            impact=0.8,
            detection_rate=0.9,
            false_positive_rate=0.1,
            residual_loss=0.05,
            decision="skip",
            verification=Verification(
                verdict="FAIL" if index % 2 else "PASS", reason="test assertion"
            ),
            audit_only=True,
            verifier_cost=0.02,
            false_alarm_cost=0.1,
            error_label=index % 2,
            label_scope="semantic",
            label_source="unit-test assertion",
            state_before="before",
            restored_hash="before",
        )
        values.update(updates)
        return StepRecord(**values).model_dump(mode="json")

    return make
