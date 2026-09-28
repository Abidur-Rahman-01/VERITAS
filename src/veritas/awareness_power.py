"""Graded-pilot power simulation of binary, paired, repository-clustered trials."""

from collections import Counter
from pathlib import Path

import numpy as np

from .awareness import ARMS
from .awareness_analysis import CONTRASTS, factorial_summary, study_rows
from .io import write_json


def _clusters(rows):
    """Keep every task/repetition and all four arms together inside its repository."""
    grouped = {}
    repetitions = Counter((r["task_id"], r["arm"]) for r in rows)
    for row in rows:
        key = (row["repository_id"], row["task_id"], row["repetition"])
        values = grouped.setdefault(key, np.zeros(4))
        values[ARMS.index(row["arm"])] = float(row["resolved"])
    result = []
    for repo in sorted({r["repository_id"] for r in rows}):
        keys = sorted(k for k in grouped if k[0] == repo)
        result.append((np.array([grouped[k] for k in keys]),
                       np.array([1/repetitions[(k[1], "00")] for k in keys])))
    return result


def simulate_power(clusters, weights, target_arm, effect, repositories, *, rng,
                   simulations, bootstrap_samples, alpha, missing_probability=0):
    """Empirical cluster resampling plus prespecified Bernoulli flips in one arm.

    This is a pilot-based planning model, not evidence of a treatment effect. The
    attainable alternative is centered on the requested contrast in expectation.
    Unknown outcomes use the frozen conservative system metric in the simulation.
    """
    total_weight = sum(w.sum() for _, w in clusters)
    means = sum((y*w[:, None]).sum(axis=0) for y, w in clusters)/total_weight
    target = effect - (means @ weights - means[target_arm])
    if not 0 <= target <= 1:
        return {"power": None, "status": "alternative_outside_binary_support"}
    base = float(means[target_arm])
    change = target-base
    flip = change/(1-base) if change > 0 else -change/base if change < 0 else 0
    detected = 0
    unknown_counts = []
    for _ in range(simulations):
        sums, denominators, missing = [], [], 0
        for index in rng.integers(0, len(clusters), repositories):
            original, task_weights = clusters[index]
            y = original.copy()
            candidates = y[:, target_arm] == (0 if change > 0 else 1)
            switches = (rng.random(len(y)) < flip) & candidates
            y[switches, target_arm] = 1 if change > 0 else 0
            unknown = rng.random(y.shape) < missing_probability
            missing += int(unknown.sum())
            y[unknown] = 0
            sums.append((y*task_weights[:, None]).sum(axis=0))
            denominators.append(task_weights.sum())
        sums, denominators = np.asarray(sums), np.asarray(denominators)
        sample = rng.integers(0, repositories, (bootstrap_samples, repositories))
        draws = (sums[sample].sum(axis=1)/denominators[sample].sum(axis=1)[:, None]) @ weights
        low, high = np.quantile(draws, [alpha/2, 1-alpha/2])
        detected += int(low > 0 or high < 0)
        unknown_counts.append(missing)
    estimate = detected/simulations
    return {"power": estimate, "status": "simulated", "target_arm_success": float(target),
            "monte_carlo_se": float(np.sqrt(estimate*(1-estimate)/simulations)),
            "mean_unknown_outcomes": float(np.mean(unknown_counts))}


def pilot_power(root, repositories=(10, 20, 40, 80), effects=None, simulations=2000,
                missing_probabilities=(0.0, 0.05, 0.15), bootstrap_samples=199):
    plan, spec, rows = study_rows(root)
    if spec.partition not in {"development", "pilot"} or spec.design != "factorial":
        raise ValueError("Power planning requires a development/pilot factorial")
    if any(r["resolved"] is None for r in rows):
        raise ValueError("Power planning requires graded pilot outcomes, not behavioral proxies")
    if (not repositories or simulations < 100 or bootstrap_samples < 100
            or any(n < 2 for n in repositories)):
        raise ValueError("Use at least 100 simulations/bootstrap draws and two repositories")
    effects = effects if effects is not None else [spec.meaningful_effect]
    if not effects or any(not 0 < e < 1 for e in effects):
        raise ValueError("Minimum meaningful effects must be in (0,1)")
    if not missing_probabilities or any(not 0 <= p < 1 for p in missing_probabilities):
        raise ValueError("Missingness scenarios must lie in [0,1)")
    # Validate the complete design before building arrays or resampling.
    factorial_summary(rows, spec.seed, 100, spec.alpha)
    focal = {"awareness": 1, "feedback": 2, "feedback_cued": 3,
             "interaction": 3, "combined": 3}
    rng = np.random.default_rng(spec.seed)
    results = {}
    for actor in spec.actors:
        selected = [r for r in rows if r["actor_id"] == actor.id]
        clusters = _clusters(selected)
        if len(clusters) < 2:
            raise ValueError("Power planning needs multiple graded repository clusters")
        baseline = np.concatenate([y[:, 0] for y, _ in clusters])
        zero_variance = bool(np.var(baseline) == 0)
        sizes = np.array([len(y) for y, _ in clusters])
        grand = baseline.mean()
        between = sum(len(y)*(y[:, 0].mean()-grand)**2 for y, _ in clusters)/(len(clusters)-1)
        residual_df = len(baseline)-len(clusters)
        within = sum(((y[:, 0]-y[:, 0].mean())**2).sum() for y, _ in clusters)/residual_df \
            if residual_df else None
        n0 = (len(baseline)-(sizes**2).sum()/len(baseline))/(len(clusters)-1)
        denominator = between+(n0-1)*within if within is not None else 0
        scenarios = []
        for n in repositories:
            for name, weights in CONTRASTS.items():
                alpha = spec.alpha if name == spec.primary_contrast else spec.alpha/4
                for effect in effects:
                    for missing in missing_probabilities:
                        result = simulate_power(clusters, np.asarray(weights), focal[name], effect, n,
                            rng=rng, simulations=simulations, bootstrap_samples=bootstrap_samples,
                            alpha=alpha, missing_probability=missing)
                        scenarios.append({"repositories": n, "contrast": name, "mde": effect,
                            "missing_probability": missing, "alpha": alpha,
                            "endpoint": "repair_success" if missing == 0 else "system_success",
                            **result})
        results[actor.id] = {"pilot_repositories": len(clusters),
            "baseline_success": float(grand), "zero_baseline_variance": zero_variance,
            "descriptive_baseline_icc": float((between-within)/denominator)
            if denominator > 0 else None,
            "paired_cell_covariance": np.cov(np.concatenate([y for y, _ in clusters]).T).tolist(),
            "scenarios": scenarios}
    result = {"study_id": plan["study_id"], "actors": results, "simulations": simulations,
        "bootstrap_samples": bootstrap_samples,
        "method": "Binary paired trials resampled by repository; percentile-bootstrap decisions",
        "limitations": "Pilot-dependent planning model; within-repository patterns are empirical. "
        "Alternatives flip one prespecified arm to the requested mean contrast. Missingness grid "
        "assumes independent missing grades and evaluates conservative system success. Small or "
        "degenerate pilots need broader recruitment and sensitivity assumptions; these outputs "
        "do not automatically choose a confirmatory sample size."}
    write_json(Path(root) / "report" / "power.json", result)
    return result
