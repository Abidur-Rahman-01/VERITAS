"""Delivery policies (experimental arms) and the harness that applies them.

Every arm sees the same evidence (all producers run at every checkpoint and are charged
equally) and uses the same renderer and token cap. Arms differ only in which items they deliver.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .agent import CheckpointState, Packet
from .backend import Backend
from .config import FAMILIES, CostConfig, EvidenceConfig
from .evidence import OBSERVED_FAMILIES, EvidenceBank, EvidenceItem, render_packet
from .features import feature_record, hidden_features, logprob_features, state_features
from .probe import Predictor
from .producers import ProducerContext, Producers, extract_json

FAMILY_ORDER = {f: i for i, f in enumerate(FAMILIES)}
LINUCB_ACTIONS = {
    "none": (),
    "failure": ("F1", "F2"),
    "diagnostic": ("F3", "F4"),
    "opinion": ("F5", "F6", "F7"),
    "all": tuple(FAMILIES),
}


def canonical_order(items: list[EvidenceItem]) -> list[EvidenceItem]:
    return sorted(items, key=lambda i: (FAMILY_ORDER[i.family], -i.severity, i.evidence_id))


@dataclass
class Selection:
    items: list[EvidenceItem]
    decision: dict = field(default_factory=dict)
    credits: float = 0.0


@dataclass
class PolicyContext:
    state: CheckpointState
    items: list[EvidenceItem]
    rng: random.Random
    count_tokens: Callable[[str], int]
    token_cap: int
    credit_cap: float
    cost: CostConfig


class Policy:
    name = "base"

    def select(self, ctx: PolicyContext) -> Selection:
        raise NotImplementedError


class NonePolicy(Policy):
    name = "NONE"

    def select(self, ctx):
        return Selection([], {"reason": "withhold all"})


class AllPolicy(Policy):
    name = "ALL"

    def select(self, ctx):
        return Selection(canonical_order(ctx.items))


class FixPolicy(Policy):
    """Continuity with the v1 fixed actionable template: failure + traceback cards only."""

    name = "FIX"

    def select(self, ctx):
        chosen = [i for i in ctx.items if i.family in ("F1", "F2")]
        return Selection(sorted(chosen, key=lambda i: (-i.severity, i.family, i.evidence_id)))


def _records(ctx: PolicyContext, hidden: list | None) -> list[dict]:
    return [
        feature_record(item, ctx.state, len(ctx.items), ctx.credit_cap, ctx.count_tokens,
                       hidden[k] if hidden else None)
        for k, item in enumerate(ctx.items)
    ]


class ManiplePolicy(Policy):
    """MANIPLE-style per-instance selection on non-hidden features (strongest prior selector)."""

    name = "MANIPLE"

    def __init__(self, predictor: Predictor):
        if predictor.needs_hidden:
            raise ValueError("MANIPLE baseline must use a predictor without hidden features")
        self.predictor = predictor

    def select(self, ctx):
        if not ctx.items:
            return Selection([])
        proba, _ = self.predictor.predict(_records(ctx, None))
        ranked = sorted(zip(ctx.items, proba), key=lambda t: -t[1])
        chosen = [item for item, p in ranked if p > 0.5]
        return Selection(chosen, {"proba": {i.evidence_id: float(p) for i, p in ranked}})


class GatePolicy(Policy):
    """Proposed: deliver items whose predicted marginal value exceeds tau (with redundancy)."""

    name = "GATE"

    def __init__(self, predictor: Predictor, backend: Backend, tau: float):
        self.predictor = predictor
        self.backend = backend
        self.tau = tau

    def scored(self, ctx: PolicyContext) -> tuple[list[tuple[EvidenceItem, float]], float]:
        if not ctx.items:
            return [], 0.0
        hidden, credits = None, 0.0
        if self.predictor.needs_hidden:
            hidden, tokens = hidden_features(self.backend, ctx.state, ctx.items, ctx.token_cap,
                                             ctx.count_tokens)
            credits = tokens * ctx.cost.per_token
            if any(h is None for h in hidden):
                return [(item, float("nan")) for item in ctx.items], credits
        _, value = self.predictor.predict(_records(ctx, hidden))
        return list(zip(ctx.items, (float(v) for v in value))), credits

    def choose(self, scored: list[tuple[EvidenceItem, float]]) -> list[EvidenceItem]:
        chosen: list[EvidenceItem] = []
        for item, value in sorted(scored, key=lambda t: -t[1]):
            if not np.isfinite(value):
                continue
            penalty = self.predictor.redundancy_lambda * sum(
                1 for c in chosen if c.family == item.family
            )
            if value - penalty > self.tau:
                chosen.append(item)
        return chosen

    def select(self, ctx):
        scored, credits = self.scored(ctx)
        if scored and all(not np.isfinite(v) for _, v in scored):
            return Selection([], {"reason": "features unavailable; abstain"}, credits)
        chosen = self.choose(scored)
        return Selection(chosen, {"value": {i.evidence_id: v for i, v in scored},
                                  "tau": self.tau}, credits)


class RandomSameSizePolicy(Policy):
    """G1 control: as many items as GATE would deliver, chosen uniformly at random."""

    name = "RANDOM_SAME_SIZE"

    def __init__(self, gate: GatePolicy):
        self.gate = gate

    def select(self, ctx):
        scored, credits = self.gate.scored(ctx)
        k = len(self.gate.choose(scored))
        chosen = ctx.rng.sample(ctx.items, k) if k else []
        return Selection(canonical_order(chosen), {"k": k}, credits)


class ShuffledPolicy(Policy):
    """G3 control: same family composition as ALL, but each item comes from another task."""

    name = "SHUFFLED"

    def __init__(self, donors: list[EvidenceItem]):
        self.by_family: dict[str, list[EvidenceItem]] = {}
        for item in donors:
            self.by_family.setdefault(item.family, []).append(item)

    def select(self, ctx):
        chosen, mapping = [], {}
        task = ctx.items[0].task_id if ctx.items else ""
        for item in canonical_order(ctx.items):
            pool = [d for d in self.by_family.get(item.family, []) if d.task_id != task]
            if pool:
                donor = ctx.rng.choice(pool)
                chosen.append(donor)
                mapping[item.evidence_id] = donor.evidence_id
        return Selection(chosen, {"donor_map": mapping})


VERIFIER_PROMPT = (
    "Issue:\n{issue}\n\nA model wrote this finding about the bug:\n{finding}\n\n"
    'Rate how likely the finding is correct and useful for fixing the issue. Reply with JSON '
    '{{"score": <number between 0 and 1>}} and nothing else.'
)


class QualityPolicy(Policy):
    """SHERLOC-style gate: observed evidence always; opinions only if a patch-free verifier
    (the resident model) scores them at or above the threshold."""

    name = "QUALITY"

    def __init__(self, backend: Backend, threshold: float, issue: str, max_new_tokens: int):
        self.backend = backend
        self.threshold = threshold
        self.issue = issue
        self.max_new_tokens = max_new_tokens

    def select(self, ctx):
        chosen, scores, tokens = [], {}, 0
        for item in canonical_order(ctx.items):
            if item.family in OBSERVED_FAMILIES:
                chosen.append(item)
                continue
            finding = f"{item.claim}\n{item.location}\n{item.observed}".strip()
            gen = self.backend.generate(
                [{"role": "user", "content": VERIFIER_PROMPT.format(
                    issue=self.issue[:4000], finding=finding)}],
                None, seed=0, temperature=0.0, max_new_tokens=self.max_new_tokens,
            )
            tokens += gen.prompt_tokens + gen.completion_tokens
            data = extract_json(gen.text) or {}
            try:
                score = float(data.get("score"))
            except (TypeError, ValueError):
                score = 0.0
            scores[item.evidence_id] = score
            if score >= self.threshold:
                chosen.append(item)
        return Selection(chosen, {"verifier": scores}, tokens * ctx.cost.per_token)


class LinUCB:
    """Disjoint LinUCB. Trained offline with full information (every action's reward is a
    labelled subset value), then frozen (alpha=0) for evaluation."""

    def __init__(self, actions: list[str], dim: int, ridge: float = 1.0):
        self.actions = actions
        self.dim = dim
        self.A = {a: np.eye(dim) * ridge for a in actions}
        self.b = {a: np.zeros(dim) for a in actions}

    def update(self, action: str, x: np.ndarray, reward: float) -> None:
        self.A[action] += np.outer(x, x)
        self.b[action] += reward * x

    def scores(self, x: np.ndarray, alpha: float = 0.0) -> dict[str, float]:
        out = {}
        for a in self.actions:
            inv = np.linalg.inv(self.A[a])
            theta = inv @ self.b[a]
            out[a] = float(theta @ x + alpha * np.sqrt(x @ inv @ x))
        return out

    def select(self, x: np.ndarray, available: list[str], alpha: float = 0.0) -> str:
        scores = self.scores(x, alpha)
        return max(sorted(available), key=lambda a: scores[a])

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({
            "actions": self.actions, "dim": self.dim,
            "A": {a: self.A[a].tolist() for a in self.actions},
            "b": {a: self.b[a].tolist() for a in self.actions},
        }))

    @classmethod
    def load(cls, path: str | Path) -> "LinUCB":
        data = json.loads(Path(path).read_text())
        model = cls(data["actions"], data["dim"])
        model.A = {a: np.asarray(v) for a, v in data["A"].items()}
        model.b = {a: np.asarray(v) for a, v in data["b"].items()}
        return model


def linucb_context(state: CheckpointState, items: list[EvidenceItem],
                   credit_cap: float) -> np.ndarray:
    counts = [float(sum(1 for i in items if i.family == f)) for f in FAMILIES]
    return np.asarray([1.0] + state_features(state, len(items), credit_cap)
                      + logprob_features(state) + counts)


class LinUCBPolicy(Policy):
    name = "LINUCB"

    def __init__(self, model: LinUCB):
        self.model = model

    def select(self, ctx):
        x = linucb_context(ctx.state, ctx.items, ctx.credit_cap)
        present = {i.family for i in ctx.items}
        available = [a for a, fams in LINUCB_ACTIONS.items()
                     if not fams or present & set(fams)]
        action = self.model.select(x, available, alpha=0.0)
        families = set(LINUCB_ACTIONS[action])
        chosen = canonical_order([i for i in ctx.items if i.family in families])
        return Selection(chosen, {"action": action})


class OraclePolicy(Policy):
    """Analysis bound only: best family subset by AEV_LL, computed with outcome-plane refs."""

    name = "ORACLE"

    def __init__(self, oracle: Callable[[CheckpointState, list[EvidenceItem]], tuple[list, float]]):
        self.oracle = oracle

    def select(self, ctx):
        families, credits = self.oracle(ctx.state, ctx.items)
        chosen = canonical_order([i for i in ctx.items if i.family in set(families)])
        return Selection(chosen, {"oracle_families": list(families)}, credits)


class EvidenceHarness:
    """Runs producers, applies the validity rule, asks the policy, renders the packet."""

    def __init__(self, producers: Producers, policy: Policy, task_id: str, problem: str,
                 environment_hash: str, ev_cfg: EvidenceConfig, cost: CostConfig,
                 credit_cap: float, count_tokens: Callable[[str], int], seed: int,
                 preset: tuple[str, list[EvidenceItem], float] | None = None):
        self.producers = producers
        self.policy = policy
        self.task_id = task_id
        self.problem = problem
        self.environment_hash = environment_hash
        self.ev_cfg = ev_cfg
        self.cost = cost
        self.credit_cap = credit_cap
        self.count_tokens = count_tokens
        self.rng = random.Random(seed)
        self.seed = seed
        self.bank = EvidenceBank()
        self.preset = preset  # (tree_hash, items, producer credits) for a restored checkpoint
        self.last_items: list[EvidenceItem] = []
        self.last_producer_credits = 0.0
        self.producer_errors: list[str] = []

    def collect(self, state: CheckpointState) -> tuple[list[EvidenceItem], float]:
        if self.preset and self.preset[0] == state.tree_hash:
            items, credits = self.preset[1], self.preset[2]
            self.preset = None
            for item in items:
                self.bank.add(item)
        else:
            ctx = ProducerContext(
                task_id=self.task_id, problem_statement=self.problem,
                checkpoint_id=f"{self.task_id}:{state.index}:{state.tree_hash[:12]}",
                tree_hash=state.tree_hash, environment_hash=self.environment_hash,
                diff=state.diff, seed=self.seed,
            )
            out = self.producers.produce(ctx)
            self.producer_errors += out.errors
            for item in out.items:
                self.bank.add(item)
            credits = out.credits
        self.bank.expire_except(state.tree_hash, self.environment_hash)
        return self.bank.current(state.tree_hash, self.environment_hash), credits

    def __call__(self, state: CheckpointState) -> Packet:
        items, producer_credits = self.collect(state)
        self.last_items, self.last_producer_credits = items, producer_credits
        ctx = PolicyContext(state, items, self.rng, self.count_tokens,
                            self.ev_cfg.packet_token_cap, self.credit_cap, self.cost)
        selection = self.policy.select(ctx)
        text, included, tokens = render_packet(selection.items, state.index,
                                               self.ev_cfg.packet_token_cap, self.count_tokens)
        decision = {"policy": self.policy.name, "available": [i.evidence_id for i in items],
                    "selected": [i.evidence_id for i in selection.items],
                    "packet_tokens": tokens, **selection.decision}
        return Packet(text, included, producer_credits + selection.credits, decision)
