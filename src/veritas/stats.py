"""Statistics for paired, clustered designs."""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
from scipy.stats import binomtest, norm, spearmanr


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the discordant counts b (A only) and c (B only)."""
    n = b + c
    if n == 0:
        return 1.0
    return float(binomtest(b, n, 0.5, alternative="two-sided").pvalue)


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values (monotone, capped at 1)."""
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(ordered)
    adjusted, running = {}, 0.0
    for rank, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - rank) * p))
        adjusted[name] = running
    return adjusted


def mcnemar_pairs_needed(p_discordant: float, delta: float, alpha: float = 0.05,
                         power: float = 0.8) -> float:
    """Approximate number of pairs to detect a paired risk difference ``delta``."""
    if not 0 < delta < p_discordant <= 1:
        return math.inf
    za, zb = norm.ppf(1 - alpha / 2), norm.ppf(power)
    return (za * math.sqrt(p_discordant) + zb * math.sqrt(p_discordant - delta**2)) ** 2 / delta**2


def cluster_bootstrap(clusters: list[str], statistic, n_boot: int = 5000, seed: int = 0,
                      level: float = 0.95) -> tuple[float, float]:
    """Percentile CI resampling whole clusters; ``statistic(indices)`` returns a float."""
    groups: dict[str, list[int]] = defaultdict(list)
    for i, cluster in enumerate(clusters):
        groups[cluster].append(i)
    keys = sorted(groups)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n_boot):
        picked = rng.choice(len(keys), size=len(keys), replace=True)
        indices = [i for k in picked for i in groups[keys[k]]]
        value = statistic(indices)
        if value is not None and np.isfinite(value):
            draws.append(value)
    if not draws:
        return (math.nan, math.nan)
    lo, hi = np.percentile(draws, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(lo), float(hi)


def paired_contrast(a: list[int], b: list[int], clusters: list[str], n_boot: int = 5000,
                    seed: int = 0) -> dict:
    """Paired binary outcomes for arms A and B on the same blocks."""
    a_arr, b_arr = np.asarray(a), np.asarray(b)
    only_a = int(((a_arr == 1) & (b_arr == 0)).sum())
    only_b = int(((a_arr == 0) & (b_arr == 1)).sum())

    def diff(indices):
        return float(a_arr[indices].mean() - b_arr[indices].mean())

    return {
        "n": len(a), "rate_a": float(a_arr.mean()) if len(a) else math.nan,
        "rate_b": float(b_arr.mean()) if len(b) else math.nan,
        "difference": diff(list(range(len(a)))) if len(a) else math.nan,
        "only_a": only_a, "only_b": only_b,
        "discordance": (only_a + only_b) / len(a) if len(a) else math.nan,
        "mcnemar_p": mcnemar_exact(only_a, only_b),
        "ci95": cluster_bootstrap(clusters, diff, n_boot, seed) if len(a) else (math.nan,) * 2,
    }


def ratio_contrast(num_a, den_a, num_b, den_b, clusters, n_boot=5000, seed=0) -> dict:
    """Difference in ratio-of-sums (e.g. resolved per credit) with a cluster bootstrap CI."""
    arrays = [np.asarray(x, dtype=float) for x in (num_a, den_a, num_b, den_b)]

    def diff(indices):
        na, da, nb, db = (x[indices].sum() for x in arrays)
        if da <= 0 or db <= 0:
            return None
        return float(na / da - nb / db)

    return {"difference": diff(list(range(len(clusters)))),
            "ci95": cluster_bootstrap(clusters, diff, n_boot, seed)}


def safe_spearman(a, b) -> float | None:
    """Spearman's rho, or None when it is undefined (fewer than 3 pairs or a constant input)."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if len(a) < 3 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return None
    rho = spearmanr(a, b).statistic
    return float(rho) if np.isfinite(rho) else None
