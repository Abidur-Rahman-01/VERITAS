"""Runtime-legal feature construction for evidence-value prediction.

Inputs are restricted to ``CheckpointState`` (what the harness sees) and ``EvidenceItem``
(runtime fields only). Nothing from the outcome plane can enter: ``tests/test_features.py``
asserts that the feature names never mention outcome-plane quantities.
"""

from __future__ import annotations

import math

import numpy as np

from .agent import CheckpointState
from .backend import Backend
from .evidence import EvidenceItem, render_packet
from .tasks import patch_files
from .tools import TOOLS

FAMILIES = ("F1", "F2", "F3", "F4", "F5", "F6", "F7")
ITEM_COLUMNS = [f"fam_{f}" for f in FAMILIES] + [
    "opinion", "log_render_tokens", "severity", "n_tests", "touches_diff_file",
    "log_observed_chars", "has_location",
]
STATE_COLUMNS = ["checkpoint_index", "step", "remaining_credits", "log_history_chars",
                 "n_items", "log_diff_lines"]
LOGPROB_COLUMNS = ["mean_logprob", "min_logprob", "mean_entropy", "logprob_missing"]
OUTCOME_PLANE_WORDS = ("gold", "reference", "grade", "resolved", "aev", "hidden_test",
                       "fail_to_pass", "pass_to_pass", "bug_discriminative")


def item_features(item: EvidenceItem, state: CheckpointState,
                  count_tokens) -> list[float]:
    diff_files = set(patch_files(state.diff))
    card_tokens = count_tokens(item.claim + "\n" + item.observed + "\n" + item.location)
    location_file = item.location.split("::")[0].split(":")[0]
    return [float(item.family == f) for f in FAMILIES] + [
        float(item.basis == "model_opinion"),
        math.log1p(card_tokens),
        item.severity,
        float(len(item.tests)),
        float(bool(diff_files & set(item.affected_files)) or location_file in diff_files),
        math.log1p(len(item.observed)),
        float(bool(item.location)),
    ]


def state_features(state: CheckpointState, n_items: int, credit_cap: float) -> list[float]:
    history = sum(len(str(m.get("content") or "")) for m in state.messages)
    return [
        float(state.index), float(state.step),
        max(0.0, state.remaining_credits) / credit_cap if credit_cap else 0.0,
        math.log1p(history), float(n_items), math.log1p(state.diff.count("\n")),
    ]


def logprob_features(state: CheckpointState) -> list[float]:
    rows = [r for r in state.recent_logprobs if r.get("mean_logprob") is not None]
    if not rows:
        return [0.0, 0.0, 0.0, 1.0]
    mean = float(np.mean([r["mean_logprob"] for r in rows]))
    low = float(min(r["min_logprob"] for r in rows if r.get("min_logprob") is not None))
    entropies = [r["mean_entropy"] for r in rows if r.get("mean_entropy") is not None]
    return [mean, low, float(np.mean(entropies)) if entropies else 0.0, 0.0]


def hidden_features(backend: Backend, state: CheckpointState, items: list[EvidenceItem],
                    token_cap: int, count_tokens) -> tuple[list[list[float] | None], int]:
    """Δ hidden state per item: state(h ⊕ packet({e})) − state(h ⊕ neutral packet).

    Returns one flattened vector per item (None when unavailable) and the number of packet tokens
    processed, which the caller charges as harness cost.
    """
    prompts, charged = [], 0
    for chosen in [[]] + [[item] for item in items]:
        text, _, tokens = render_packet(chosen, state.index, token_cap, count_tokens)
        prompts.append(state.messages + [{"role": "user", "content": text}])
        charged += tokens
    results = backend.features(prompts, TOOLS)
    base = results[0]
    out: list[list[float] | None] = []
    for result in results[1:]:
        if base.error or result.error or not result.hidden:
            out.append(None)
            continue
        delta = np.concatenate([np.asarray(h) - np.asarray(b)
                                for h, b in zip(result.hidden, base.hidden)])
        out.append(delta.astype(np.float32).tolist())
    return out, charged


def feature_record(item: EvidenceItem, state: CheckpointState, n_items: int, credit_cap: float,
                   count_tokens, hidden: list[float] | None) -> dict:
    return {
        "item": item_features(item, state, count_tokens),
        "state": state_features(state, n_items, credit_cap),
        "logprob": logprob_features(state),
        "hidden": hidden,
    }


def matrix(records: list[dict], feature_set: str) -> np.ndarray:
    """Assemble the design matrix for a named feature set (see ablations R1-R6)."""
    parts = {
        "item": ["item"],
        "logprob": ["logprob"],
        "hidden": ["hidden"],
        "full": ["item", "state", "logprob", "hidden"],
        "full_no_state": ["item", "logprob", "hidden"],
        "no_hidden": ["item", "state", "logprob"],
        "item_state": ["item", "state"],
    }[feature_set]
    rows = []
    for record in records:
        row: list[float] = []
        for part in parts:
            value = record[part]
            if value is None:
                raise ValueError(f"record lacks {part} features")
            row += list(value)
        rows.append(row)
    return np.asarray(rows, dtype=np.float32)
