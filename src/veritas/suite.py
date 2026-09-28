"""Sequential, frozen parameter sweeps over the real transactional runtime."""
import csv
import itertools
import json
from pathlib import Path

import yaml
from pydantic import Field

from .comparison import (
    ComparisonConfig,
    create_plan,
    discover_models,
    read_plan,
    report_comparison,
    run_comparison,
)
from .eligibility import eligible_models
from .io import digest, write_json
from .plots import plot_comparison
from .schema import StrictModel


class SuiteConfig(StrictModel):
    comparison: ComparisonConfig
    # Dotted Config fields, plus comparison.verification_budget and comparison.seed.
    grid: dict[str, list] = Field(default_factory=dict)
    verifier_model: str | None = None
    max_variants: int = Field(default=128, gt=0)


def variants(spec):
    keys = sorted(spec.grid)
    count = 1
    for key in keys:
        values = spec.grid[key]
        if not values or len({digest(v) for v in values}) != len(values):
            raise ValueError(f"Grid values must be nonempty and unique: {key}")
        section, separator, field = key.partition(".")
        if not separator or not field or "." in field or section not in {
            "model", "critic", "verifier", "run", "graph", "sandbox", "comparison"
        }:
            raise ValueError(f"Invalid grid field: {key}")
        if section == "comparison" and field not in {"verification_budget", "seed"}:
            raise ValueError(f"Unsupported comparison grid field: {key}")
        if section == "run" and field in {
            "policy", "verification_budget", "score_critic", "audit_all",
            "allow_uncalibrated", "dynamic_lambda", "threshold"
        }:
            raise ValueError(f"{key} is controlled by comparison policies/calibration")
        count *= len(values)
    if count > spec.max_variants:
        raise ValueError(f"Grid has {count} variants; max_variants={spec.max_variants}")
    return [dict(zip(keys, values)) for values in itertools.product(*(spec.grid[k] for k in keys))]


def create_suite(config, output):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Suite output must be empty; use --resume for an existing suite")
    spec = SuiteConfig.model_validate(yaml.safe_load(Path(config).read_text()))
    combinations = variants(spec)
    models, excluded = discover_models(spec.comparison.server, spec.comparison.models)
    models, size_excluded = eligible_models(
        spec.comparison.server, models, spec.comparison.max_parameters_b
    )
    excluded.extend(size_excluded)
    entries = []
    for index, parameters in enumerate(combinations):
        comparison = spec.comparison.model_dump(mode="json")
        comparison["models"] = [m["name"] for m in models]
        if spec.verifier_model:
            verifier = (
                max(models, key=lambda m: m.get("parameter_count") or 0)["name"]
                if spec.verifier_model == "auto" else spec.verifier_model
            )
            comparison["runtime_overrides"].setdefault("verifier", {}).update({
                "backend": spec.comparison.server.backend,
                "base_url": spec.comparison.server.base_url,
                "api_key_env": spec.comparison.server.api_key_env,
                "name": verifier,
            })
        for key, value in parameters.items():
            section, field = key.split(".")
            if section == "comparison":
                comparison[field] = value
            else:
                comparison["runtime_overrides"].setdefault(section, {})[field] = value
        name = f"variant-{index:03d}-{digest(parameters)[:8]}"
        directory = output / name
        directory.mkdir(parents=True)
        config_path = directory / "comparison.yaml"
        config_path.write_text(yaml.safe_dump(comparison))
        plan = create_plan(config_path, directory)
        entries.append({"variant": name, "parameters": parameters, "plan_id": plan["plan_id"]})
    manifest = {"version": 1, "variants": entries, "excluded_models": excluded}
    manifest["suite_id"] = digest(manifest)
    write_json(output / "suite.json", manifest)
    print(f"Frozen {len(entries)} variants. Run with: veritas suite --output '{output}' --resume")
    return manifest


def read_suite(output):
    manifest = json.loads((Path(output) / "suite.json").read_text())
    if digest({k: v for k, v in manifest.items() if k != "suite_id"}) != manifest["suite_id"]:
        raise ValueError("Suite manifest changed since planning")
    for entry in manifest["variants"]:
        if read_plan(Path(output) / entry["variant"])["plan_id"] != entry["plan_id"]:
            raise ValueError("Suite child plan changed")
    return manifest


def report_suite(output):
    output = Path(output)
    rows = []
    for entry in read_suite(output)["variants"]:
        for row in report_comparison(output / entry["variant"]):
            rows.append({"variant": entry["variant"], "parameters": entry["parameters"], **row})
    write_json(output / "suite-results.json", rows)
    with (output / "suite-results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    plot_comparison(rows, output / "plots")
    return rows


def run_suite(output, retry_failed=False):
    for entry in read_suite(output)["variants"]:
        run_comparison(Path(output) / entry["variant"], retry_failed=retry_failed)
    return report_suite(output)
