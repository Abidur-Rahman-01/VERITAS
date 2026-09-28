import pytest

from veritas.awareness import read_study
from veritas.awareness_costs import model_costs
from veritas.awareness_store import StudyStore
from veritas.schema import Usage


def test_frozen_prices_separate_roles_and_preserve_unknown_costs(awareness_setup):
    f = awareness_setup
    root = f.create(model_prices={
        "actor": {"input_per_million": 2, "output_per_million": 4, "per_call": .01,
                  "source": "fixture actor rate"},
        "reviewer": {"input_per_million": 5, "output_per_million": 10,
                     "source": "fixture reviewer rate"}})
    _, spec, _, jobs = read_study(root)
    trial = jobs[0].trial_id
    with StudyStore(root) as db:
        for role in ("actor_draft", "actor_revision", "online_review", "confidence_final",
                     "defensive_intent_draft", "shadow_audit"):
            call = db.reserve_call(trial, role, 200, spec)
            db.finish_call(call, Usage(prompt_tokens=100, completion_tokens=50,
                cpu_seconds=2, gpu_seconds=3, resource_source="fixture"), "fixture", "completed")
        costs = model_costs(db, spec, trial, "actor")
        assert costs["deployed_model_money"] == pytest.approx(2 * .0104 + .001)
        assert costs["measurement_model_money"] == pytest.approx(.0104 + 2 * .001)
        assert costs["deployed_model_cpu_seconds"] == 6
        assert costs["measurement_model_gpu_seconds"] == 9
        db.reserve_call(trial, "actor_revision", 200, spec)  # Response was lost.
        costs = model_costs(db, spec, trial, "actor")
        assert costs["deployed_model_money"] is None
        assert costs["deployed_model_gpu_seconds"] is None
        assert costs["coverage"]["deployed"]["priced_calls"] == 3
        assert costs["measurement_model_money"] == pytest.approx(.0124)


def test_tokens_and_wall_time_do_not_imply_pricing_or_resource_measurements(awareness_setup):
    root = awareness_setup.create()
    _, spec, _, jobs = read_study(root)
    with StudyStore(root) as db:
        call = db.reserve_call(jobs[0].trial_id, "actor_draft", 20, spec)
        db.finish_call(call, Usage(prompt_tokens=10, completion_tokens=5, seconds=3),
                       "fixture", "completed")
        costs = model_costs(db, spec, jobs[0].trial_id, "actor")
        assert costs["deployed_model_money"] is None
        assert costs["deployed_model_cpu_seconds"] is None
        assert costs["deployed_model_gpu_seconds"] is None
        assert costs["measurement_model_money"] == 0  # No measurement calls incurred.
