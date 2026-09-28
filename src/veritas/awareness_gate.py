"""Frozen post-repair admission: development fit, independent calibration, locked test."""

import json
import time
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from .awareness_analysis import study_rows
from .awareness_store import StudyStore, coordinator_lock
from .io import digest, write_json

FEATURES = ("added_lines", "deleted_lines", "files_changed", "test_functions_added",
            "test_functions_modified")


def _write_frozen(path, obj):
    if Path(path).exists():
        raise ValueError("Gate artifact exists; use a new path")
    obj["artifact_id"] = digest(obj)
    write_json(path, obj)
    return obj


def read_gate(path):
    obj = json.loads(Path(path).read_text())
    if digest({k: v for k, v in obj.items() if k != "artifact_id"}) != obj["artifact_id"]:
        raise ValueError("Frozen gate artifact changed")
    return obj


def _features(row):
    metrics = row["outcome"].get("metrics", {}).get("final", {})
    if any(metrics.get(key) is None for key in FEATURES):
        return None
    values = np.asarray([metrics[key] for key in FEATURES], dtype=float)
    if not np.all(np.isfinite(values)) or np.any(values < 0):
        return None
    return np.log1p(values)


def _score(row, model):
    if model.get("features") != list(FEATURES):
        raise ValueError("Gate scorer feature definition differs from this implementation")
    features = _features(row)
    if features is None:
        return None
    features = (features - np.asarray(model["center"])) / np.asarray(model["scale"])
    logit = float(features @ model["coefficients"] + model["intercept"])
    return float(1 / (1 + np.exp(-np.clip(logit, -700, 700))))


def fit_gate(root, output):
    plan, spec, rows = study_rows(root)
    if spec.partition not in {"development", "pilot"} or spec.design != "factorial":
        raise ValueError("Gate score fitting requires development/pilot factorial data")
    usable = [r for r in rows if r["resolved"] is not None and _features(r) is not None]
    if len(usable) < 4:
        raise ValueError("Gate fitting requires at least four independently graded patches")
    x = np.array([_features(r) for r in usable])
    y = np.array([1-int(r["resolved"]) for r in usable])
    center, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1
    if len(set(y)) == 1:
        probability = (y.sum()+1)/(len(y)+2)
        coefficients, intercept = np.zeros(len(FEATURES)), np.log(probability/(1-probability))
        method = "smoothed_constant_one_class"
    else:
        fit = LogisticRegression(C=1.0, random_state=spec.seed, max_iter=1000).fit((x-center)/scale, y)
        coefficients, intercept = fit.coef_[0], fit.intercept_[0]
        method = "logistic_regression"
    return _write_frozen(output, {"version": 1, "kind": "score", "method": method,
        "features": list(FEATURES), "center": center.tolist(), "scale": scale.tolist(),
        "coefficients": coefficients.tolist(), "intercept": float(intercept),
        "fit_study": plan["study_id"], "fit_outcomes_hash": digest(rows),
        "fit_repositories": sorted({r["repository_id"] for r in rows}),
        "used_patches": len(usable), "excluded_unknown_or_unscorable": len(rows)-len(usable),
        "thresholds": [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]})


def _repository_metrics(rows, scores, threshold):
    values = {}
    for row in rows:
        score = scores[row["trial_id"]]
        admitted = threshold is not None and score is not None and score <= threshold
        y = row["resolved"]
        vector = [int(admitted and y is False), int(admitted and y is not True), int(admitted)]
        values.setdefault(row["repository_id"], []).append(vector)
    return np.array([np.mean(values[r], axis=0) for r in sorted(values)])


def calibrate_gate(model_path, root, confirmation, output, alpha=0.05, delta=0.05):
    if not 0 < alpha < 1 or not 0 < delta < 1:
        raise ValueError("Risk target and error probability must be in (0,1)")
    model = read_gate(model_path)
    plan, spec, rows = study_rows(root)
    target_plan, target_spec, target_rows = study_rows(confirmation)
    if model["kind"] != "score" or spec.partition != "calibration" or spec.design != "factorial":
        raise ValueError("Use a frozen development scorer and calibration factorial")
    if target_spec.partition != "confirmation" or target_spec.design != "factorial":
        raise ValueError("Gate must be locked to a confirmation plan")
    if any(r["resolved"] is not None for r in target_rows):
        raise ValueError("Confirmation grades already opened; cannot calibrate retrospectively")
    fit_repos = set(model["fit_repositories"])
    cal_repos = {r["repository_id"] for r in rows}
    test_repos = {r["repository_id"] for r in target_rows}
    if fit_repos & cal_repos or fit_repos & test_repos or cal_repos & test_repos:
        raise ValueError("Gate fit/calibration/confirmation repositories overlap")
    # Check the actual intervention and actors, not just friendly model names.
    for key in ("actors", "reviewer", "draft", "revision", "review", "grader", "compact",
                "disclosure_probability", "assignment_probability", "input_chars",
                "control", "neutral_control_text"):
        if spec.model_dump()[key] != target_spec.model_dump()[key]:
            raise ValueError(f"Calibration and confirmation protocols differ in {key}")
    if any(r["runtime_status"] not in {"completed", "failed", "interrupted", "budget_stopped"}
           for r in rows):
        raise ValueError("Finish the calibration actor batch before choosing thresholds")
    scores = {r["trial_id"]: _score(r, model) for r in rows}
    candidates = []
    for a in (False, True):
        for d in (None, False, True):
            sample = [r for r in rows if r["actual_assignment"] == a and
                      (d is None or r["disclosure_assigned"] == d)]
            if not sample:
                raise ValueError("Calibration strata are empty")
            candidates.append((a, d, sample))
    # Familywise bound over all tested thresholds, A strata and D/pooled populations.
    tests = len(candidates)*len(model["thresholds"])
    policies = []
    for a, d, sample in candidates:
        grid = []
        for threshold in model["thresholds"]:
            clusters = _repository_metrics(sample, scores, threshold)
            upper = min(1.0, float(clusters[:, 1].mean()) +
                        float(np.sqrt(np.log(tests/delta)/(2*len(clusters)))))
            grid.append({"threshold": threshold, "upper_risk": upper,
                         "coverage": float(clusters[:, 2].mean())})
        admissible = [x for x in grid if x["upper_risk"] <= alpha]
        chosen = max(admissible, key=lambda x: (x["coverage"], -x["upper_risk"], -x["threshold"])) \
            if admissible else {"threshold": None, "upper_risk": 0.0, "coverage": 0.0}
        policies.append({"actual_assignment": a, "calibration_disclosure": d,
                         "chosen": chosen, "candidates": grid,
                         "status": ("certified_candidate" if spec.repository_sampling ==
                                    "independent_population" else "descriptive_cohort_candidate")
                         if admissible else "defer_all_insufficient_evidence"})
    artifact = {"version": 1, "kind": "calibrated", "model": model, "policies": policies,
        "alpha": alpha, "delta": delta, "family_tests": tests,
        "method": "simultaneous Hoeffding bound on equal-repository unresolved-admission loss",
        "repository_sampling": spec.repository_sampling,
        "population_certification": spec.repository_sampling == "independent_population",
        "assumptions": "Independent repositories from the same target population; fixed candidate "
        "family. Conditional-D bounds do not transfer across disclosure shifts automatically.",
        "calibration_study": plan["study_id"], "calibration_outcomes_hash": digest(rows),
        "calibration_repositories": sorted(cal_repos), "confirmation_study": target_plan["study_id"]}
    with coordinator_lock(confirmation), StudyStore(confirmation) as db:
        if db.artifact("gate_lock"):
            raise ValueError("Confirmation gate already locked")
        # Recheck within the lock so a concurrent grader cannot race threshold freezing.
        if db.db.execute("SELECT 1 FROM artifacts WHERE name LIKE 'grade/%' LIMIT 1").fetchone():
            raise ValueError("Confirmation grading has already started")
        result = _write_frozen(output, artifact)
        db.put_artifact("gate_lock", {"artifact_id": result["artifact_id"],
                                     "confirmation_study": target_plan["study_id"]})
    return result


def report_gate(gate_path, root):
    gate = read_gate(gate_path)
    plan, spec, rows = study_rows(root)
    if gate["kind"] != "calibrated" or gate["confirmation_study"] != plan["study_id"]:
        raise ValueError("Gate is not frozen for this confirmation study")
    with StudyStore(root) as db:
        lock = db.artifact("gate_lock")
        if not lock or lock["artifact_id"] != gate["artifact_id"]:
            raise ValueError("Gate lock mismatch")
    start = time.monotonic()
    scores = {r["trial_id"]: _score(r, gate["model"]) for r in rows}
    score_seconds = time.monotonic()-start
    rng = np.random.default_rng(spec.seed)
    estimates = []
    cluster_estimates = {}
    for policy in gate["policies"]:
        for d in (False, True):
            sample = [r for r in rows if r["actual_assignment"] == policy["actual_assignment"]
                      and r["disclosure_assigned"] == d]
            clusters = _repository_metrics(sample, scores, policy["chosen"]["threshold"])
            cluster_estimates[(policy["actual_assignment"], policy["calibration_disclosure"], d)] = clusters
            low, high, coverage = clusters.mean(axis=0)
            draws = clusters[rng.integers(0, len(clusters),
                (spec.bootstrap_samples, len(clusters)))].mean(axis=1) if len(clusters) > 1 else None
            # An unknown declined patch cannot change the admission loss. In
            # particular, defer-all has known zero risk even without any grades.
            unknown = bool(np.any(clusters[:, 0] != clusters[:, 1]))
            interval = np.quantile(draws[:, 0], [0.025, 0.975]).tolist() \
                if draws is not None and not unknown else None
            estimates.append({"calibration_disclosure": policy["calibration_disclosure"],
                "disclosure": d, "actual_assignment": policy["actual_assignment"],
                "threshold": policy["chosen"]["threshold"], "assigned": len(sample),
                "unknown_grades": sum(r["resolved"] is None for r in sample),
                "score_failures": sum(scores[r["trial_id"]] is None for r in sample),
                "admitted": sum(policy["chosen"]["threshold"] is not None and
                    scores[r["trial_id"]] is not None and
                    scores[r["trial_id"]] <= policy["chosen"]["threshold"] for r in sample),
                "repositories": len(clusters), "risk": None if unknown else float(low),
                "risk_bounds": [float(low), float(high)], "risk_ci95": interval,
                "coverage": float(coverage), "conditional_failure":
                float(low/coverage) if coverage and not unknown else None,
                "conditional_failure_bounds": [float(low/coverage), float(high/coverage)]
                if coverage else None,
                "coverage_ci95": np.quantile(draws[:, 2], [0.025, 0.975]).tolist()
                if draws is not None else None,
                "target_gap_ci95": [x-gate["alpha"] for x in interval] if interval else None,
                "target_gap": None if unknown else float(low-gate["alpha"]),
                "target_gap_bounds": [float(low-gate["alpha"]), float(high-gate["alpha"])]})
    transfers = []
    for a in (False, True):
        for source in (False, True):
            pair = {e["disclosure"]: e for e in estimates if e["actual_assignment"] == a and
                    e["calibration_disclosure"] == source}
            target = not source
            source_clusters = cluster_estimates[(a, source, source)]
            target_clusters = cluster_estimates[(a, source, target)]
            shift_interval = None
            if len(source_clusters) > 1 and pair[source]["risk"] is not None and pair[target]["risk"] is not None:
                indices = rng.integers(0, len(source_clusters),
                    (spec.bootstrap_samples, len(source_clusters)))
                paired = target_clusters[:, 0] - source_clusters[:, 0]
                shift_interval = np.quantile(paired[indices].mean(axis=1), [0.025, 0.975]).tolist()
            transfers.append({"actual_assignment": a, "direction": f"{int(source)}->{int(target)}",
                "risk_shift_ci95": shift_interval,
                "risk_shift": None if pair[source]["risk"] is None or pair[target]["risk"] is None
                else pair[target]["risk"]-pair[source]["risk"],
                "bounds": [pair[target]["risk_bounds"][0]-pair[source]["risk_bounds"][1],
                           pair[target]["risk_bounds"][1]-pair[source]["risk_bounds"][0]]})
    comparison = []
    for a in (False, True):
        for d in (False, True):
            pooled = next(e for e in estimates if e["actual_assignment"] == a and
                          e["disclosure"] == d and e["calibration_disclosure"] is None)
            aware = next(e for e in estimates if e["actual_assignment"] == a and
                         e["disclosure"] == d and e["calibration_disclosure"] == d)
            comparison.append({"actual_assignment": a, "disclosure": d,
                "aware_minus_pooled_coverage": aware["coverage"]-pooled["coverage"],
                "aware_minus_pooled_risk": aware["risk"]-pooled["risk"]
                if aware["risk"] is not None and pooled["risk"] is not None else None,
                "risk_difference_bounds": [aware["risk_bounds"][0]-pooled["risk_bounds"][1],
                                           aware["risk_bounds"][1]-pooled["risk_bounds"][0]]})
    result = {"study_id": plan["study_id"], "gate_id": gate["artifact_id"],
        "estimates": estimates, "transfer": transfers, "scoring_seconds": score_seconds,
        "disclosure_aware_vs_pooled": comparison,
        "scores": scores, "score_inputs_hash": digest([
            {"trial_id": r["trial_id"], "final_patch_hash": r["outcome"].get("final_patch_hash"),
             "metrics": r["outcome"].get("metrics", {}).get("final")} for r in rows]),
        "scoring_model_calls": 0, "weighting": "equal repositories",
        "interpretation": "Static final-patch admission; not unsafe-action risk or adaptive feedback value"}
    write_json(Path(root) / "report" / "gate-report.json", result)
    return result
