"""Whole pipeline on real git repositories with a scripted actor (no GPU, no Docker)."""

import json

from veritas.analysis import analyze
from veritas.config import ARMS, StudyConfig
from veritas.ledger import Ledger
from veritas.study import Study


def test_full_study_pipeline(tmp_path, dataset, fake_backend):
    cfg = StudyConfig.model_validate({
        "study_id": "e2e",
        "root": str(tmp_path / "runs"),
        "sandbox": {"kind": "local", "command_timeout_seconds": 60, "grade_timeout_seconds": 120},
        "agent": {"max_steps": 10},
        "evidence": {"test_timeout_seconds": 60},
        "data": {"dataset_path": str(dataset), "created_after": "2025-01-01"},
        "screen": {"seeds": [0, 1, 2, 3], "min_successes": 1, "max_successes": 3},
        "collect_seeds": [10, 11],
        "validate": {"n_checkpoints": 4, "seeds_per_arm": 1},
        "probe": {"models": ["logistic"], "feature_sets": ["item", "full"], "folds": 2},
        "confirm": {"seeds": [20], "arms": list(ARMS), "bootstrap_samples": 200},
    })
    study = Study(cfg, backend=fake_backend)
    assert study.prepare()["eligible"] == 8
    assert study.validate_gold()["failed"] == 0
    assert study.gold_valid() == set(study.tasks)
    assert study.screen()["failed"] == 0
    zpd = study.zpd_tasks()
    assert zpd, "the scripted actor should put most tasks in the ZPD"
    counts = study.make_split()
    assert counts["train"] > 0 and counts["confirm"] > 0
    split = study.split()
    repo_part = {}
    for task_id, part in split.items():
        repo = study.tasks[task_id].repo
        assert repo_part.setdefault(repo, part) == part  # repository-disjoint

    assert study.collect()["failed"] == 0
    keys = study.checkpoint_keys()
    assert keys
    export = json.loads((study.dir / "checkpoints" / f"{keys[0]}.json").read_text())
    assert export["items"] and export["snapshot_id"]

    label = study.label()
    assert label["failed"] == 0, list(study.ledger.events("unit_error"))[-1:]
    labels = json.loads((study.dir / "labels" / f"{keys[0]}.json").read_text())
    assert labels["rows"][0]["kind"] == "family_subset"

    assert study.validate()["failed"] == 0, list(study.ledger.events("unit_error"))[-1:]
    report = study.train()
    assert {"gate", "maniple", "linucb"} <= set(report["artifacts"]), report["skipped"]

    assert study.parents()["failed"] == 0, list(study.ledger.events("unit_error"))[-1:]
    confirm = study.confirm()
    assert confirm["failed"] == 0, list(study.ledger.events("unit_error"))[-1:]
    arms_seen = {r["arm"] for r in study.rows("confirm.jsonl")}
    assert arms_seen == set(ARMS)

    # Resuming does no new work.
    assert study.confirm()["ran"] == 0

    result = analyze(study.dir, cfg)
    assert result["RQ1"]["n_items"] > 0
    assert result["RQ4"]["n_blocks"] > 0
    assert (study.dir / "analysis" / "report.md").read_text().startswith("# VERITAS report")
    Ledger(study.dir / "ledger.jsonl").verify()

    # Evidence moves the scripted actor: ALL recovers wrong parents, NONE cannot.
    rows = study.rows("confirm.jsonl")
    wrong = [r for r in rows if r["parent_status"] == "unresolved"]
    if wrong:
        rate = {arm: sum(r["grade"]["status"] == "resolved" for r in wrong if r["arm"] == arm)
                for arm in ("ALL", "NONE")}
        assert rate["ALL"] > rate["NONE"] == 0
