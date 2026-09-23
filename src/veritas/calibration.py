import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import expit

from .io import file_hash, read_records, write_json


def calibration_metrics(logits, labels, temperature=1.0, bins=15):
    z, y = np.asarray(logits, dtype=float), np.asarray(labels, dtype=float)
    if not len(y) or len(z) != len(y) or not np.isfinite(z).all() or not np.isin(y, [0, 1]).all():
        raise ValueError("Calibration requires finite logits and binary labels")
    p = expit(z / temperature)
    ece = 0.0
    for i in range(bins):
        mask = (p >= i / bins) & ((p < (i + 1) / bins) if i < bins - 1 else (p <= 1))
        if mask.any():
            ece += mask.mean() * abs(p[mask].mean() - y[mask].mean())
    return {
        "n": len(y),
        "ece": float(ece),
        "brier": float(np.mean((p - y) ** 2)),
        "nll": float(np.mean(np.logaddexp(0, z / temperature) - y * z / temperature)),
    }


def fit_temperature(logits, labels):
    z, y = np.asarray(logits, dtype=float), np.asarray(labels, dtype=float)
    calibration_metrics(z, y)
    if len(set(y)) != 2:
        raise ValueError("Temperature fitting requires both correct and erroneous actions")

    def objective(log_t):
        scaled = z / math.exp(log_t)
        return np.mean(np.logaddexp(0, scaled) - y * scaled)

    result = minimize_scalar(objective, bounds=(-4.6, 4.6), method="bounded")
    if not result.success:
        raise RuntimeError("Temperature optimizer failed")
    return math.exp(result.x)


def wilson(success, total, z=1.96):
    if not total:
        return [0.0, 1.0]
    p = success / total
    center = (p + z * z / (2 * total)) / (1 + z * z / total)
    width = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return [max(0.0, center - width), min(1.0, center + width)]


def fit_artifact(records_path, output, scope="semantic", min_class_samples=5):
    records = list(read_records(records_path))
    # A task may never straddle fitting/evaluation partitions, even for repeated runs.
    seen = defaultdict(set)
    roles = defaultdict(set)
    for row in records:
        seen[row["group_id"]].add(row["split"])
        if row["split"] == "calib":
            roles[row["group_id"]].add(row.get("calibration_role"))
    if any(len(x) > 1 for x in seen.values()) or any(len(x) > 1 for x in roles.values()):
        raise ValueError("Task/group leakage across data partitions")
    probability = [
        r
        for r in records
        if r["split"] == "calib"
        and r.get("calibration_role") == "probability"
        and r.get("label_scope") == scope
        and r.get("error_label") is not None
        and r.get("raw_logit") is not None
        and not r.get("blocked")
    ]
    if len(probability) < 10:
        raise ValueError(
            "Need at least 10 independently labeled probability-calibration actions; no labels are fabricated"
        )
    z = [r["raw_logit"] for r in probability]
    y = [r["error_label"] for r in probability]
    temperature = fit_temperature(z, y)
    stat_rows = [
        r
        for r in records
        if r["split"] == "calib"
        and r.get("calibration_role") == "verifier_stats"
        and r.get("label_scope") == scope
        and r.get("error_label") is not None
        and not r.get("blocked")
    ]
    critic_ids = {r.get("critic_id") for r in probability + stat_rows}
    verifier_ids = {r.get("verifier_id") for r in probability + stat_rows}
    if len(critic_ids) != 1 or len(verifier_ids) != 1:
        raise ValueError("Calibration cannot mix critic or verifier configurations")
    if any(not r.get("verification") or r["verification"]["verdict"] == "ERROR" for r in stat_rows):
        raise ValueError(
            "Verifier statistics require complete successful audit coverage; collect audit_all traces"
        )
    grouped = defaultdict(list)
    for row in stat_rows:
        grouped[row["action"]["action_class"]].append(row)
    statistics = {}
    for cls, rows in grouped.items():
        bad = [r for r in rows if r["error_label"] == 1]
        good = [r for r in rows if r["error_label"] == 0]
        if min(len(bad), len(good)) < min_class_samples:
            continue
        tp = sum(r["verification"]["verdict"] == "FAIL" for r in bad)
        fp = sum(r["verification"]["verdict"] == "FAIL" for r in good)
        recovered = [r for r in bad if r.get("restored_hash") and r.get("state_before")]
        # Recovery estimates are restricted to observable workspace state, not external consequences.
        if not recovered:
            continue
        rho = sum(r["restored_hash"] != r["state_before"] for r in recovered) / len(recovered)
        statistics[cls] = {
            "detection_rate": tp / len(bad),
            "false_positive_rate": fp / len(good),
            "residual_loss": rho,
            "errors": len(bad),
            "correct": len(good),
            "detection_ci95": wilson(tp, len(bad)),
            "false_positive_ci95": wilson(fp, len(good)),
            "recovery_n": len(recovered),
            "recovery_scope": "workspace_hash_only",
        }
    if not statistics:
        raise ValueError(
            "No class has enough positive/negative labels AND measured restoration. Collect more natural traces"
        )
    artifact = {
        "version": 1,
        "method": "temperature",
        "temperature": temperature,
        "critic_id": next(iter(critic_ids)),
        "verifier_id": next(iter(verifier_ids)),
        "label_scope": scope,
        "statistics": statistics,
        "before": calibration_metrics(z, y),
        "after": calibration_metrics(z, y, temperature),
        "fit_groups": sorted({r["group_id"] for r in probability + stat_rows}),
        "source_sha256": file_hash(Path(records_path)),
        "minimum_per_class_outcome": min_class_samples,
    }
    write_json(output, artifact)
    return artifact


def apply_artifact(row, artifact):
    if row.get("raw_logit") is None or not row.get("action"):
        raise ValueError("Record lacks pre-action score or contract")
    cls = row["action"]["action_class"]
    if row.get("critic_id") != artifact.get("critic_id") or row.get("verifier_id") != artifact.get(
        "verifier_id"
    ):
        raise ValueError("Record critic/verifier identity differs from calibration")
    if cls not in artifact["statistics"]:
        raise ValueError(
            f"No empirical verifier/recovery statistics for {cls}; do not silently invent them"
        )
    stat = artifact["statistics"][cls]
    return {
        **row,
        "p_error": float(expit(row["raw_logit"] / artifact["temperature"])),
        **{k: stat[k] for k in ("detection_rate", "false_positive_rate", "residual_loss")},
    }
