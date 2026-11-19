"""Command line: one sub-command per study phase. Run them in order; each is resumable."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .config import load_config

PHASES = [
    ("prepare", "Load and filter tasks; write tasks.jsonl and its manifest."),
    ("validate-gold", "Grade every gold patch; tasks the grader cannot reproduce are dropped."),
    ("screen", "Bare-actor attempts on screening seeds (zone-of-proximal-development filter)."),
    ("split", "Repository-disjoint train/dev/confirm split of ZPD tasks."),
    ("collect", "NONE-harness rollouts on train/dev tasks; export every checkpoint."),
    ("label", "AEV_LL labels, runtime features and bug-discrimination labels."),
    ("validate", "Branched rollouts for AEV_RO on a stratified checkpoint sample."),
    ("train", "Cross-validated predictors, baselines, frozen GATE/MANIPLE/LinUCB artifacts."),
    ("parents", "Confirmation parents: run each confirm task to its first checkpoint."),
    ("confirm", "Branch every parent into every arm under matched budgets."),
    ("analyze", "RQ1-RQ4 report (analysis/report.md and report.json)."),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="veritas", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch-data", help="Download the pinned dataset and exclusion ids.")
    fetch.add_argument("--config", required=True)
    fetch.add_argument("--force", action="store_true", help="re-download an existing dataset")
    serve = sub.add_parser("serve", help="Start the single-GPU model server.")
    serve.add_argument("--config", required=True)
    for name, text in PHASES:
        p = sub.add_parser(name, help=text)
        p.add_argument("--config", required=True)
        p.add_argument("--workers", type=int, default=1,
                       help="parallel units (sandbox work overlaps; the model server serialises)")
        if name == "split":
            p.add_argument("--reuse-split", help="split.json of another study (same repositories)")
        if name == "analyze":
            p.add_argument("--other", nargs="*", default=[],
                           help="run directories of other actors whose checkpoints this study "
                           "cross-labelled (H1c)")
    cross = sub.add_parser("cross-label", help="Score another study's checkpoints (H1c).")
    cross.add_argument("--config", required=True)
    cross.add_argument("--source", required=True, help="run directory of the other study")
    cross.add_argument("--workers", type=int, default=1)
    status = sub.add_parser("status", help="Verify the ledger and summarise progress.")
    status.add_argument("--config", required=True)
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    if args.command == "fetch-data":
        from .datafetch import fetch

        print(json.dumps(fetch(cfg.data, force=args.force), indent=2))
        return 0
    if args.command == "serve":
        from .hfserver import serve as run_server

        run_server(cfg.server)
        return 0
    if args.command == "status":
        from .ledger import Ledger

        ledger = Ledger(cfg.run_dir / "ledger.jsonl")
        done = Counter(e["unit"] for e in ledger.events("unit_done"))
        errors = Counter(e["unit"] for e in ledger.events("unit_error"))
        print(json.dumps({"ledger": "verified", "done": done, "errors": errors}, indent=2))
        return 0

    from .study import Study

    study = Study(cfg, workers=getattr(args, "workers", 1))
    handlers = {
        "prepare": study.prepare,
        "validate-gold": study.validate_gold,
        "screen": study.screen,
        "split": lambda: study.make_split(args.reuse_split),
        "collect": study.collect,
        "label": study.label,
        "validate": study.validate,
        "train": study.train,
        "parents": study.parents,
        "confirm": study.confirm,
        "cross-label": lambda: study.cross_label(args.source),
    }
    if args.command == "analyze":
        from .analysis import analyze

        report = analyze(cfg.run_dir, cfg, [Path(o) for o in args.other])
        print((cfg.run_dir / "analysis" / "report.md").read_text())
        return 0 if report else 1
    result = handlers[args.command]()
    print(json.dumps(result, indent=2, default=str)[:20000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
