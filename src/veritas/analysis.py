"""RQ1-RQ4 analysis and the report (docs/ARCHITECTURE.md §7)."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .stats import (
    cluster_bootstrap,
    holm,
    mcnemar_pairs_needed,
    paired_contrast,
    ratio_contrast,
    safe_spearman,
)
from .util import atomic_write_json, atomic_write_text, read_json, read_jsonl


def _rows(path: Path) -> list[dict]:
    return list(read_jsonl(path)) if path.exists() else []


def _rate_ci(values: list[float], clusters: list[str], predicate, n_boot: int) -> dict:
    flags = np.asarray([1.0 if predicate(v) else 0.0 for v in values])
    if not len(flags):
        return {"n": 0, "rate": None, "ci95": None}
    ci = cluster_bootstrap(clusters, lambda idx: float(flags[idx].mean()), n_boot)
    return {"n": int(len(flags)), "rate": float(flags.mean()), "ci95": list(ci)}


def rq1(run: Path, splits: dict[str, str], repos: dict[str, str], n_boot: int) -> dict:
    items, item_repos, families = [], [], []
    summaries, shapley_by_family = [], defaultdict(list)
    bsg: dict[str, bool | None] = {}
    for path in sorted((run / "bsg").glob("*.json")) if (run / "bsg").exists() else []:
        bsg.update(read_json(path))
    two_by_two = Counter()
    for path in sorted((run / "labels").glob("*.json")) if (run / "labels").exists() else []:
        label = read_json(path)
        task_id = label["checkpoint_key"].rsplit("__", 2)[0]
        if splits.get(task_id) not in ("train", "dev"):
            continue
        for row in label["items"]:
            if row["aev_single"] is None:
                continue
            items.append(row["aev_single"])
            item_repos.append(repos[task_id])
            families.append(row["family"])
            disc = bsg.get(row["evidence_id"])
            if disc is not None:
                two_by_two[(bool(disc), row["aev_single"] > 0)] += 1
        if label.get("summary"):
            summaries.append(label["summary"])
            for family, value in label["summary"]["shapley"].items():
                shapley_by_family[family].append(value)
    by_family = {}
    for family in sorted(set(families)):
        values = [v for v, f in zip(items, families) if f == family]
        by_family[family] = {"n": len(values), "mean_aev": float(np.mean(values)),
                             "harm_rate": float(np.mean([v <= 0 for v in values])),
                             "mean_shapley": float(np.mean(shapley_by_family[family]))
                             if shapley_by_family[family] else None}
    a, b = two_by_two[(True, True)], two_by_two[(True, False)]
    c, d = two_by_two[(False, True)], two_by_two[(False, False)]
    odds = ((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5)) if sum(two_by_two.values()) else None
    return {
        "n_items": len(items),
        "harm_rate_H1a": _rate_ci(items, item_repos, lambda v: v <= 0, n_boot),
        "by_family": by_family,
        "n_checkpoints_with_subsets": len(summaries),
        "non_monotone_share_H1b": float(np.mean([s["non_monotone"] for s in summaries]))
        if summaries else None,
        "mean_interaction": float(np.mean([s["interaction"] for s in summaries]))
        if summaries else None,
        "discriminative_x_valuable_H5": {
            "disc_and_valuable": a, "disc_not_valuable": b, "nondisc_valuable": c,
            "nondisc_not_valuable": d, "odds_ratio_haldane": odds,
        },
    }


def cross_actor(run: Path, other: Path) -> dict:
    """H1c: Spearman of single-item AEV between this run's labels of ``other``'s checkpoints
    (``cross_labels/<other>/``) and ``other``'s own labels."""
    other_id = read_json(other / "config.json")["config"]["study_id"]
    mine_dir = run / "cross_labels" / other_id
    pairs = []
    for path in sorted(mine_dir.glob("*.json")) if mine_dir.exists() else []:
        theirs_path = other / "labels" / path.name
        if not theirs_path.exists():
            continue
        mine = {r["evidence_id"]: r["aev_single"] for r in read_json(path)["items"]}
        theirs = {r["evidence_id"]: r["aev_single"] for r in read_json(theirs_path)["items"]}
        for key, value in mine.items():
            if value is not None and theirs.get(key) is not None:
                pairs.append((value, theirs[key]))
    rho = safe_spearman([p[0] for p in pairs], [p[1] for p in pairs])
    return {"n_pairs": len(pairs), "spearman": rho}


def rq2(run: Path, repos: dict[str, str], n_boot: int) -> dict:
    rows = [r for r in _rows(run / "validate.jsonl")
            if r["grade"]["status"] in ("resolved", "unresolved")]
    if not rows:
        return {"n_branches": 0}
    plan = {c["key"]: c for c in read_json(run / "validate_plan.json")}
    outcome = defaultdict(list)
    by_seed = {}
    for r in rows:
        resolved = int(r["grade"]["status"] == "resolved")
        outcome[(r["checkpoint_key"], r["arm"])].append(resolved)
        by_seed[(r["checkpoint_key"], r["arm"], r["seed"])] = resolved
    ll, ro = [], []
    for key, candidate in plan.items():
        if (key, "NONE") not in outcome:
            continue
        base = np.mean(outcome[(key, "NONE")])
        label = read_json(run / "labels" / f"{key}.json")
        full = next((r["aev_ll"] for r in label["rows"]
                     if r["kind"] == "family_subset" and r["key"] == label["families"]), None)
        estimates = {"TOP": candidate["top"]["aev_single"],
                     "BOTTOM": candidate["bottom"]["aev_single"], "ALL": full}
        for arm, value in estimates.items():
            if (key, arm) in outcome and value is not None:
                ll.append(value)
                ro.append(float(np.mean(outcome[(key, arm)]) - base))
    top, bottom, clusters = [], [], []
    for (key, arm, seed), value in by_seed.items():
        if arm == "TOP" and (key, "BOTTOM", seed) in by_seed:
            top.append(value)
            bottom.append(by_seed[(key, "BOTTOM", seed)])
            clusters.append(repos[key.rsplit("__", 2)[0]])
    return {
        "n_branches": len(rows), "n_pairs_ll_ro": len(ll),
        "spearman_ll_ro_H2": safe_spearman(ll, ro),
        "top_vs_bottom": paired_contrast(top, bottom, clusters, n_boot) if top else None,
    }


def _confirm_table(run: Path) -> tuple[dict, dict, dict]:
    parents = _rows(run / "parents.jsonl")
    branches = _rows(run / "confirm.jsonl")
    outcome: dict[tuple, int] = {}
    credits: dict[tuple, float] = {}
    for b in branches:
        if b["grade"]["status"] in ("resolved", "unresolved"):
            block = (b["task_id"], b["checkpoint_key"].rsplit("__", 2)[1])
            outcome[(block, b["arm"])] = int(b["grade"]["status"] == "resolved")
            credits[(block, b["arm"])] = float(b["credits"])
    info = {}
    for p in parents:
        block = (p["task_id"], str(p["seed"]))
        info[block] = {"repo": p["repo"], "parent": p["parent_grade"]["status"],
                       "has_checkpoint": p["has_checkpoint"]}
    return outcome, credits, info


def rq4(run: Path, arms: list[str], primary: tuple[str, str], secondary: list,
        margin: float, n_boot: int) -> dict:
    outcome, credits, info = _confirm_table(run)
    if not info:
        return {"n_blocks": 0}

    def value(block, arm):
        if not info[block]["has_checkpoint"]:  # no treatment possible: every arm = parent
            status = info[block]["parent"]
            return (int(status == "resolved"), 0.0) if status in ("resolved", "unresolved") \
                else (None, None)
        return outcome.get((block, arm)), credits.get((block, arm))

    def contrast(a: str, b: str, cohort: str | None) -> dict:
        xa, xb, ca, cb, cl = [], [], [], [], []
        for block, meta in sorted(info.items()):
            if cohort == "recovery" and meta["parent"] != "unresolved":
                continue
            if cohort == "regression" and meta["parent"] != "resolved":
                continue
            va, cra = value(block, a)
            vb, crb = value(block, b)
            if va is None or vb is None:
                continue
            xa.append(va)
            xb.append(vb)
            ca.append(cra)
            cb.append(crb)
            cl.append(meta["repo"])
        if not xa:
            return {"n": 0}
        out = paired_contrast(xa, xb, cl, n_boot)
        if cohort is None:
            out["resolved_per_credit"] = ratio_contrast(xa, ca, xb, cb, cl, n_boot)
        return out

    per_arm = {}
    for arm in arms:
        known = [(b, v) for (b, a), v in outcome.items() if a == arm]
        per_arm[arm] = {
            "n": len(known), "resolved_rate": float(np.mean([v for _, v in known]))
            if known else None,
            "mean_credits": float(np.mean([credits[(b, arm)] for b, _ in known]))
            if known else None,
        }
    results = {}
    for a, b in [tuple(primary)] + [tuple(s) for s in secondary]:
        name = f"{a}-{b}"
        regression = contrast(a, b, "regression")
        results[name] = {"full": contrast(a, b, None), "recovery": contrast(a, b, "recovery"),
                         "regression_cohort": regression}
        if regression.get("n"):
            # A's regression rate minus B's = -(difference in resolved rates) on correct parents.
            lo, hi = regression["ci95"]
            results[name]["regression_noninferior"] = (
                None if not np.isfinite(lo) else bool(-lo <= margin)
            )
    secondary_p = {f"{a}-{b}": results[f"{a}-{b}"]["full"].get("mcnemar_p", 1.0)
                   for a, b in [tuple(s) for s in secondary] if results[f"{a}-{b}"]["full"].get("n")}
    primary_full = results[f"{primary[0]}-{primary[1]}"]["full"]
    disc = primary_full.get("discordance")
    return {
        "n_blocks": len(info),
        "blocks_without_checkpoint": sum(1 for m in info.values() if not m["has_checkpoint"]),
        "per_arm": per_arm, "contrasts": results, "holm_secondary": holm(secondary_p),
        "pairs_needed": {f"delta_{d}": mcnemar_pairs_needed(disc, d) if disc else None
                         for d in (0.05, 0.08)},
    }


def analyze(run: Path, cfg, other_runs: list[Path] | None = None) -> dict:
    split = read_json(run / "split.json")["tasks"]
    tasks = {r["instance_id"]: r["repo"] for r in read_jsonl(run / "tasks.jsonl")}
    n_boot = cfg.confirm.bootstrap_samples
    report = {
        "study_id": cfg.study_id,
        "split_counts": read_json(run / "split.json")["counts"],
        "RQ1": rq1(run, split, tasks, n_boot),
        "RQ1_cross_actor_H1c": {str(o): cross_actor(run, o) for o in (other_runs or [])},
        "RQ2": rq2(run, tasks, n_boot),
        "RQ3": read_json(run / "train" / "report.json")
        if (run / "train" / "report.json").exists() else None,
        "RQ4": rq4(run, cfg.confirm.arms, cfg.confirm.primary, cfg.confirm.secondary,
                   cfg.confirm.regression_margin, n_boot),
    }
    atomic_write_json(run / "analysis" / "report.json", report)
    atomic_write_text(run / "analysis" / "report.md", render_markdown(report))
    return report


def _fmt(value, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return "—" if not np.isfinite(value) else f"{value:.{digits}f}"
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return f"[{_fmt(value[0])}, {_fmt(value[1])}]"
    return str(value)


def render_markdown(report: dict) -> str:
    lines = [f"# VERITAS report: {report['study_id']}", "",
             f"Split (tasks): {report['split_counts']}", "", "## RQ1 Measurement", ""]
    r1 = report["RQ1"]
    harm = r1["harm_rate_H1a"]
    lines += [f"- Items labelled: {r1['n_items']}",
              f"- Harm rate (AEV ≤ 0): {_fmt(harm['rate'])} CI {_fmt(harm['ci95'])}",
              f"- Non-monotone checkpoints: {_fmt(r1['non_monotone_share_H1b'])}",
              f"- Mean interaction: {_fmt(r1['mean_interaction'])}", "",
              "| Family | n | mean AEV | harm rate | mean Shapley |", "|---|---|---|---|---|"]
    for family, row in r1["by_family"].items():
        lines.append(f"| {family} | {row['n']} | {_fmt(row['mean_aev'])} | "
                     f"{_fmt(row['harm_rate'])} | {_fmt(row['mean_shapley'])} |")
    lines += ["", f"Discriminative × valuable: {r1['discriminative_x_valuable_H5']}", ""]
    for other, result in report["RQ1_cross_actor_H1c"].items():
        lines.append(f"- Cross-actor Spearman vs {other}: {_fmt(result['spearman'])} "
                     f"(n={result['n_pairs']})")
    r2 = report["RQ2"]
    lines += ["", "## RQ2 Validity", "",
              f"- Branches: {r2.get('n_branches', 0)}; Spearman(AEV_LL, AEV_RO): "
              f"{_fmt(r2.get('spearman_ll_ro_H2'))}"]
    if r2.get("top_vs_bottom"):
        t = r2["top_vs_bottom"]
        lines.append(f"- Top − bottom resolution: {_fmt(t['difference'])} CI {_fmt(t['ci95'])}, "
                     f"McNemar p={_fmt(t['mcnemar_p'])}")
    lines += ["", "## RQ3 Prediction", ""]
    if report["RQ3"]:
        lines += ["| model | features | AUROC | AUPRC | Spearman | pairwise | ECE |",
                  "|---|---|---|---|---|---|---|"]
        for row in sorted(report["RQ3"]["cv"], key=lambda r: -r["auroc"]):
            lines.append(f"| {row['model']} | {row['feature_set']} | {_fmt(row['auroc'])} | "
                         f"{_fmt(row['auprc'])} | {_fmt(row['spearman_value'])} | "
                         f"{_fmt(row['pairwise_accuracy'])} | {_fmt(row['ece_calibrated'])} |")
        lines.append(f"\nBaselines: {report['RQ3']['baselines']}")
    r4 = report["RQ4"]
    lines += ["", "## RQ4 Control", ""]
    if r4.get("n_blocks"):
        lines += ["| arm | n | resolved | mean credits |", "|---|---|---|---|"]
        for arm, row in r4["per_arm"].items():
            lines.append(f"| {arm} | {row['n']} | {_fmt(row['resolved_rate'])} | "
                         f"{_fmt(row['mean_credits'], 1)} |")
        lines += ["", "| contrast | cohort | n | diff | CI95 | McNemar p |", "|---|---|---|---|---|---|"]
        for name, result in r4["contrasts"].items():
            for cohort in ("full", "recovery", "regression_cohort"):
                c = result[cohort]
                if c.get("n"):
                    lines.append(f"| {name} | {cohort} | {c['n']} | {_fmt(c['difference'])} | "
                                 f"{_fmt(c['ci95'])} | {_fmt(c['mcnemar_p'])} |")
        lines += ["", f"Holm-adjusted secondary p-values: {r4['holm_secondary']}",
                  f"Pairs needed at observed discordance: {r4['pairs_needed']}"]
    else:
        lines.append("No confirmation results yet.")
    return "\n".join(lines) + "\n"
