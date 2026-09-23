import math

import pytest

from veritas.controller import POLICIES, Budget, Controller, Risk


def risk(**updates):
    return Risk(
        **{
            **dict(
                p_error=0.8,
                impact=0.9,
                detection_rate=0.9,
                false_positive_rate=0.1,
                residual_loss=0.05,
                verifier_cost=0.02,
                false_alarm_cost=0.1,
            ),
            **updates,
        }
    )


def test_equation():
    assert risk().delta == pytest.approx(0.8 * 0.9 * 0.95 * 0.9 - 0.02 - 0.2 * 0.1 * 0.1)


@pytest.mark.parametrize("policy", POLICIES)
def test_no_policy_exceeds_budget(policy):
    controller = Controller(policy, 0.1, threshold=0.5 if policy == "random" else 0)
    for _ in range(100):
        if controller.decide(risk()):
            controller.reserve(risk())
    assert 0 <= controller.budget.spent <= controller.budget.total


def test_decimal_boundary():
    budget = Budget(0.3)
    for _ in range(3):
        budget.charge(0.1)
    assert budget.remaining == 0
    with pytest.raises(ValueError):
        budget.charge(0.00001)


@pytest.mark.parametrize("value", [-1, math.nan, math.inf])
def test_invalid_budget(value):
    with pytest.raises(ValueError):
        Budget(value)


def test_zero_recovery_benefit_does_not_trigger_vov():
    assert not Controller("rcvov", 1).decide(risk(residual_loss=1))


def test_lambda_tightens_with_spending():
    controller = Controller("rcvov", 0.1, dynamic_lambda=10)
    assert controller.decide(risk())
    for _ in range(4):
        controller.reserve(risk())
    assert not controller.decide(risk())


def test_invalid_costs():
    with pytest.raises(ValueError):
        risk(verifier_cost=0)
    with pytest.raises(ValueError):
        risk(p_error=math.nan)
