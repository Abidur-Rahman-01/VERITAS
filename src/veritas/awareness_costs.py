"""Frozen-price model cost views with explicit telemetry/pricing coverage."""

import json

DEPLOY_ROLES = {"actor_draft", "actor_revision", "online_review"}


def model_costs(db, spec, trial_id, actor_id):
    groups = {name: {"calls": 0, "priced_calls": 0, "observed_money": 0.0,
                    "cpu_measured_calls": 0, "gpu_measured_calls": 0,
                    "observed_cpu_seconds": 0.0, "observed_gpu_seconds": 0.0,
                    "resource_sources": []} for name in ("deployed", "measurement")}
    for row in db.db.execute("SELECT * FROM calls WHERE trial_id=?", (trial_id,)):
        group = groups["deployed" if row["role"] in DEPLOY_ROLES else "measurement"]
        group["calls"] += 1
        usage = json.loads(row["usage"]) if row["usage"] else {}
        reviewer = row["role"] in {"online_review", "shadow_audit"} or row["role"].startswith(
            "defensive_intent_")
        price = spec.model_prices.get(spec.reviewer.id if reviewer else actor_id)
        if price is not None and usage.get("measured"):
            group["priced_calls"] += 1
            group["observed_money"] += price.per_call + (
                usage["prompt_tokens"] * price.input_per_million +
                usage["completion_tokens"] * price.output_per_million) / 1_000_000
        for resource in ("cpu", "gpu"):
            measured = usage.get(f"{resource}_seconds")
            if measured is not None and usage.get("resource_source"):
                group[f"{resource}_measured_calls"] += 1
                group[f"observed_{resource}_seconds"] += measured
                group["resource_sources"].append(usage["resource_source"])
    result = {"coverage": groups}
    for name, group in groups.items():
        group["resource_sources"] = sorted(set(group["resource_sources"]))
        result[f"{name}_model_money"] = group["observed_money"] if (
            group["calls"] == group["priced_calls"]) else None
        for resource in ("cpu", "gpu"):
            result[f"{name}_model_{resource}_seconds"] = group[f"observed_{resource}_seconds"] if (
                group["calls"] == group[f"{resource}_measured_calls"]) else None
    return result
