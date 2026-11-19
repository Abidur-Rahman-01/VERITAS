"""Actor-relative evidence value (AEV): estimators and attribution.

AEV_LL(S) = max_r [log p(r | h ⊕ packet(S)) − log p(r | h ⊕ packet(∅))] / |r|   (outcome plane)

``packet(∅)`` is the neutral packet the NONE arm delivers, so labels compare exactly the
conditions a deployed harness could produce. Packets are rendered by the common renderer under
the deployment token cap; each label records which items were actually included.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Callable

from .backend import Backend, ScoreRequest
from .evidence import EvidenceItem, render_packet
from .refset import PatchError, edit_actions, materialize, reference_message, source_paths
from .tools import TOOLS


@dataclass
class Reference:
    reference_id: str
    message: dict


def all_subsets(families: list[str]) -> list[tuple[str, ...]]:
    ordered = sorted(families)
    return [c for k in range(len(ordered) + 1) for c in itertools.combinations(ordered, k)]


def shapley(values: dict[tuple[str, ...], float], players: list[str]) -> dict[str, float]:
    """Exact Shapley values for a game given on every subset (v(∅) is taken from the table)."""
    n = len(players)
    players = sorted(players)
    out = {}
    for player in players:
        others = [p for p in players if p != player]
        total = 0.0
        for k in range(len(others) + 1):
            weight = math.factorial(k) * math.factorial(n - k - 1) / math.factorial(n)
            for subset in itertools.combinations(others, k):
                with_player = tuple(sorted(subset + (player,)))
                total += weight * (values[with_player] - values[tuple(sorted(subset))])
        out[player] = total
    return out


def attribution(values: dict[tuple[str, ...], float], players: list[str],
                tolerance: float = 1e-9) -> dict:
    players = sorted(players)
    full = tuple(players)
    singles = sum(values[(p,)] for p in players)
    best = max(values, key=lambda s: (values[s], -len(s)))
    return {
        "shapley": shapley(values, players),
        "interaction": values[full] - singles,
        "value_full": values[full],
        "best_subset": list(best),
        "best_value": values[best],
        "non_monotone": values[best] > values[full] + tolerance and best != full,
    }


def build_references(base_files: dict[str, str | None], current_diff: str,
                     reference_patches: dict[str, str], fmt: str) -> list[Reference]:
    """Reference turns for one checkpoint. Patches that cannot be applied are skipped."""
    paths = sorted({p for patch in reference_patches.values() for p in source_paths(patch)})
    if not paths:
        return []
    try:
        current = materialize(base_files, current_diff, paths)
    except PatchError:
        return []
    refs = []
    for ref_id, patch in sorted(reference_patches.items()):
        own = source_paths(patch)
        try:
            patched = materialize(base_files, patch, own)
        except PatchError:
            continue
        target = {p: patched[p] for p in own}
        calls = edit_actions(current, target)
        refs.append(Reference(ref_id, reference_message(calls, current, target, fmt)))
    return refs


def packet_messages(messages: list[dict], items: list[EvidenceItem], checkpoint: int,
                    token_cap: int, count_tokens: Callable[[str], int]) -> tuple[list[dict], list]:
    text, included, _ = render_packet(items, checkpoint, token_cap, count_tokens)
    return messages + [{"role": "user", "content": text}], included


def label_checkpoint(backend: Backend, export: dict, references: list[Reference],
                     token_cap: int, count_tokens: Callable[[str], int], normalize: bool,
                     item_level: bool) -> dict:
    """Score every family subset (and item singletons/LOO) against every reference."""
    items = [EvidenceItem.model_validate(i) for i in export["items"]]
    by_family: dict[str, list[EvidenceItem]] = {}
    for item in items:
        by_family.setdefault(item.family, []).append(item)
    families = sorted(by_family)
    conditions: list[tuple[str, tuple, list[EvidenceItem]]] = []
    for subset in all_subsets(families):
        chosen = [i for f in subset for i in by_family[f]]
        conditions.append(("family_subset", subset, chosen))
    if item_level and len(items) > 1:
        for item in items:
            conditions.append(("item_single", (item.evidence_id,), [item]))
            rest = [i for i in items if i.evidence_id != item.evidence_id]
            conditions.append(("item_loo", (item.evidence_id,), rest))

    rendered = []
    for kind, key, chosen in conditions:
        msgs, included = packet_messages(export["messages"], chosen, export["index"], token_cap,
                                         count_tokens)
        rendered.append((kind, key, msgs, included))

    scores: dict[tuple[int, str], tuple[float, int]] = {}
    for ref in references:
        batch = [ScoreRequest(messages=m, reference=ref.message, tools=TOOLS)
                 for _, _, m, _ in rendered]
        for idx, result in enumerate(backend.score(batch)):
            if result.error is None and result.n_tokens > 0 and math.isfinite(result.logprob):
                scores[(idx, ref.reference_id)] = (result.logprob, result.n_tokens)

    empty_index = next(i for i, c in enumerate(rendered) if c[0] == "family_subset" and not c[1])

    def value(idx: int) -> float | None:
        best = None
        for ref in references:
            a, b = scores.get((idx, ref.reference_id)), scores.get((empty_index, ref.reference_id))
            if a is None or b is None:
                continue
            delta = a[0] - b[0]
            if normalize:
                delta /= a[1]
            best = delta if best is None else max(best, delta)
        return best

    rows = []
    for idx, (kind, key, _, included) in enumerate(rendered):
        rows.append({
            "checkpoint_key": export["checkpoint_key"], "kind": kind, "key": list(key),
            "included_ids": included, "aev_ll": value(idx),
            "logprobs": {ref.reference_id: scores.get((idx, ref.reference_id), (None, 0))[0]
                         for ref in references},
        })
    subset_values = {tuple(r["key"]): r["aev_ll"] for r in rows if r["kind"] == "family_subset"}
    summary = None
    if families and all(v is not None for v in subset_values.values()):
        summary = attribution(subset_values, families)
    singles = {r["key"][0]: r["aev_ll"] for r in rows if r["kind"] == "item_single"}
    loo = {r["key"][0]: r["aev_ll"] for r in rows if r["kind"] == "item_loo"}
    full_value = subset_values.get(tuple(families))
    item_rows = []
    for item in items:
        single = singles.get(item.evidence_id)
        if single is None and len(items) == 1:
            single = full_value
        marginal = None
        if item.evidence_id in loo and full_value is not None and loo[item.evidence_id] is not None:
            marginal = full_value - loo[item.evidence_id]
        elif len(items) == 1:
            marginal = full_value
        item_rows.append({
            "checkpoint_key": export["checkpoint_key"], "evidence_id": item.evidence_id,
            "family": item.family, "aev_single": single, "aev_marginal": marginal,
        })
    return {
        "checkpoint_key": export["checkpoint_key"], "families": families,
        "references": [r.reference_id for r in references], "rows": rows,
        "items": item_rows, "summary": summary,
    }
