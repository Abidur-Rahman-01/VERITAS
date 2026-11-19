import random

import numpy as np
import pytest
from conftest import score_fn

from veritas.aev import Reference, all_subsets, attribution, label_checkpoint, shapley
from veritas.agent import CheckpointState
from veritas.backend import FakeBackend
from veritas.config import CostConfig
from veritas.evidence import EvidenceItem
from veritas.policies import (
    AllPolicy,
    FixPolicy,
    GatePolicy,
    LinUCB,
    PolicyContext,
    RandomSameSizePolicy,
    ShuffledPolicy,
)
from veritas.probe import Predictor, cross_validate, fit_artifact, pairwise_accuracy


def test_shapley_exact_on_known_games():
    players = ["A", "B", "C"]
    additive = {s: sum({"A": 1.0, "B": 2.0, "C": -0.5}[p] for p in s) for s in all_subsets(players)}
    phi = shapley(additive, players)
    assert phi == pytest.approx({"A": 1.0, "B": 2.0, "C": -0.5})
    glove = {s: 1.0 if ("A" in s and ("B" in s or "C" in s)) else 0.0 for s in all_subsets(players)}
    phi = shapley(glove, players)
    assert phi["A"] == pytest.approx(2 / 3) and phi["B"] == pytest.approx(1 / 6)
    assert sum(phi.values()) == pytest.approx(glove[("A", "B", "C")])
    harmful = {s: (1.0 if "A" in s else 0.0) - (0.5 if "C" in s else 0.0) for s in additive}
    summary = attribution(harmful, players)
    assert summary["non_monotone"] and summary["best_subset"] == ["A"]


def _item(family, claim, basis="observed", task="t1"):
    return EvidenceItem(family=family, source="s", basis=basis, patch_hash="h",
                        environment_hash="e", claim=claim, task_id=task)


def test_label_checkpoint_values():
    items = [_item("F1", "Test x fails."), _item("F5", "maybe", "model_opinion")]
    export = {"checkpoint_key": "t1__0__1", "index": 1,
              "messages": [{"role": "user", "content": "issue"}],
              "items": [i.model_dump(mode="json") for i in items]}
    backend = FakeBackend(lambda m, s: "", scorer=score_fn)
    ref = Reference("gold", {"role": "assistant", "content": "fix"})
    result = label_checkpoint(backend, export, [ref], 1500, lambda t: len(t.split()), True, True)
    values = {tuple(r["key"]): r["aev_ll"] for r in result["rows"] if r["kind"] == "family_subset"}
    assert values[()] == 0.0
    # The packet header mentions "model opinion" once (-1); an F1 failure adds +5 nats.
    assert values[("F1",)] == pytest.approx(0.4, abs=0.02)
    assert values[("F5",)] == pytest.approx(-0.2, abs=0.02)
    assert result["summary"]["best_subset"] == ["F1"] and result["summary"]["non_monotone"]
    by_id = {r["evidence_id"]: r for r in result["items"]}
    assert by_id[items[0].evidence_id]["aev_single"] > 0
    assert by_id[items[1].evidence_id]["aev_marginal"] < 0


def _synthetic(n=400, seed=0):
    rng = np.random.default_rng(seed)
    records, values, repos, checkpoints = [], [], [], []
    for i in range(n):
        signal = rng.normal()
        records.append({"item": [signal, rng.normal()], "state": [rng.normal()],
                        "logprob": [0.0, 0.0, 0.0, 1.0], "hidden": list(rng.normal(size=4))})
        values.append(signal + 0.3 * rng.normal())
        repos.append(f"r{i % 8}")
        checkpoints.append(f"c{i // 4}")
    return records, np.asarray(values), repos, checkpoints


def test_probe_cross_validation_and_frozen_artifact(tmp_path):
    records, values, repos, checkpoints = _synthetic()
    result = cross_validate(records, values, repos, checkpoints, "logistic", "item", 4, 0.0, 0)
    assert result.metrics["auroc"] > 0.85 and result.metrics["spearman_value"] > 0.8
    sha = fit_artifact(records, values, "logistic", "item", 0.0, 0, 0.1, result.oof_proba,
                       tmp_path / "gate.joblib")
    predictor = Predictor(tmp_path / "gate.joblib", sha)
    proba, value = predictor.predict(records[:5])
    assert proba.shape == (5,) and value.shape == (5,)
    with pytest.raises(ValueError):
        Predictor(tmp_path / "gate.joblib", "0" * 64)
    assert pairwise_accuracy(["a", "a", "b"], np.array([1.0, 0.0, 3.0]),
                             np.array([0.9, 0.1, 0.0])) == 1.0


def _ctx(items):
    state = CheckpointState(1, 3, "h", "diff --git a/calc.py b/calc.py\n", [], 100.0, [])
    return PolicyContext(state, items, random.Random(0), lambda t: len(t.split()), 1500, 400.0,
                         CostConfig())


def test_fixed_policies_and_controls():
    items = [_item("F5", "op", "model_opinion"), _item("F2", "tb"), _item("F1", "fails")]
    assert [i.family for i in AllPolicy().select(_ctx(items)).items] == ["F1", "F2", "F5"]
    assert {i.family for i in FixPolicy().select(_ctx(items)).items} == {"F1", "F2"}
    donors = [_item("F1", "other fails", task="t2"), _item("F1", "same task", task="t1")]
    chosen = ShuffledPolicy(donors).select(_ctx([_item("F1", "fails")])).items
    assert [i.task_id for i in chosen] == ["t2"]


class StubPredictor:
    feature_set = "item"
    needs_hidden = False
    redundancy_lambda = 0.3

    def predict(self, records):
        values = np.asarray([r["item"][0] for r in records])  # fam_F1 one-hot -> value 1
        return values, values * 0.5


def test_gate_greedy_with_redundancy_and_random_same_size():
    items = [_item("F1", "fails a"), _item("F1", "fails b"), _item("F2", "tb")]
    # F1 items are worth 0.5 each; the second one pays the 0.3 redundancy penalty (0.2 left).
    gate = GatePolicy(StubPredictor(), backend=None, tau=0.25)
    assert [i.claim for i in gate.select(_ctx(items)).items] == ["fails a"]
    gate.tau = 0.1
    assert [i.claim for i in gate.select(_ctx(items)).items] == ["fails a", "fails b"]
    random_arm = RandomSameSizePolicy(gate).select(_ctx(items))
    assert random_arm.decision["k"] == 2 and len(random_arm.items) == 2


def test_linucb_learns_the_better_action():
    model = LinUCB(["a", "b"], 2)
    for _ in range(50):
        model.update("a", np.array([1.0, 0.0]), 1.0)
        model.update("b", np.array([1.0, 0.0]), 0.0)
        model.update("a", np.array([0.0, 1.0]), 0.0)
        model.update("b", np.array([0.0, 1.0]), 1.0)
    assert model.select(np.array([1.0, 0.0]), ["a", "b"]) == "a"
    assert model.select(np.array([0.0, 1.0]), ["a", "b"]) == "b"
