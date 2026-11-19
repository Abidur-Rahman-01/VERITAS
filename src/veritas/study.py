"""End-to-end study orchestration (Phases 1-9 of docs/ARCHITECTURE.md §6).

Every phase is resumable: each unit of work is recorded in the hash-chained ledger when it
finishes, and a re-run skips finished units. Results are appended durably to JSONL files under
``runs/<study_id>/``. Outcome-plane data (grades, references, labels) is written to files that the
runtime never reads.
"""

from __future__ import annotations

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import numpy as np

from .aev import build_references, label_checkpoint
from .agent import Agent, AgentState, CheckpointState, initial_state
from .backend import Backend, make_backend
from .bsg import discriminative_map, label_item
from .config import StudyConfig
from .energy import EnergyMeter
from .evidence import EvidenceItem
from .features import feature_record, hidden_features
from .grading import Grade, grade
from .ledger import Ledger
from .policies import (
    LINUCB_ACTIONS,
    AllPolicy,
    EvidenceHarness,
    FixPolicy,
    GatePolicy,
    LinUCB,
    LinUCBPolicy,
    ManiplePolicy,
    NonePolicy,
    OraclePolicy,
    Policy,
    QualityPolicy,
    RandomSameSizePolicy,
    Selection,
    ShuffledPolicy,
    canonical_order,
    linucb_context,
)
from .probe import Predictor, cross_validate, fit_artifact
from .producers import Producers
from .refset import read_base_files, source_paths
from .sandbox import Sandbox, open_sandbox, restore_sandbox
from .tasks import Task, load_tasks, split_by_repository
from .util import (
    append_jsonl,
    atomic_write_json,
    read_json,
    read_jsonl,
    sha256_file,
    sha256_text,
    stable_unit_interval,
    write_jsonl,
)


class StopAtCheckpoint(Exception):
    pass


class FixedThenNone(Policy):
    """Deliver the given item ids at the first (restored) checkpoint, nothing afterwards."""

    name = "FIXED"

    def __init__(self, ids: list[str]):
        self.ids = ids
        self.used = False

    def select(self, ctx):
        if self.used:
            return Selection([], {"reason": "after branching checkpoint"})
        self.used = True
        wanted = set(self.ids)
        return Selection(canonical_order([i for i in ctx.items if i.evidence_id in wanted]))


class Study:
    def __init__(self, cfg: StudyConfig, backend: Backend | None = None, workers: int = 1):
        self.cfg = cfg
        self.dir = cfg.run_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._check_config()
        self.ledger = Ledger(self.dir / "ledger.jsonl")
        self.backend = backend if backend is not None else make_backend(cfg.backend)
        self.workers = workers
        self._lock = threading.Lock()
        self._token_cache: dict[str, int] = {}
        self._tasks: dict[str, Task] | None = None

    # --- infrastructure ------------------------------------------------------------------
    def _check_config(self) -> None:
        path = self.dir / "config.json"
        current = self.cfg.model_dump(mode="json", by_alias=True)
        if path.exists():
            if read_json(path)["sha256"] != self.cfg.digest():
                raise RuntimeError(
                    f"{path} was created with a different configuration; use a new study_id"
                )
        else:
            atomic_write_json(path, {"sha256": self.cfg.digest(), "config": current})

    def path(self, *parts: str) -> Path:
        target = self.dir.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def append(self, name: str, row: dict) -> None:
        with self._lock:
            append_jsonl(self.path(name), row)

    def rows(self, name: str) -> list[dict]:
        path = self.dir / name
        return list(read_jsonl(path)) if path.exists() else []

    def count_tokens(self, text: str) -> int:
        key = sha256_text(text)
        if key not in self._token_cache:
            self._token_cache[key] = self.backend.count_tokens(text)
        return self._token_cache[key]

    @property
    def tasks(self) -> dict[str, Task]:
        if self._tasks is None:
            path = self.dir / "tasks.jsonl"
            if not path.exists():
                raise RuntimeError("run `veritas prepare` first")
            self._tasks = {r["instance_id"]: Task.model_validate(r) for r in read_jsonl(path)}
        return self._tasks

    def open(self, task: Task) -> Sandbox:
        return open_sandbox(self.cfg.sandbox, task.image, local_source=task.image)

    def grade(self, task: Task, patch: str) -> Grade:
        return grade(task, patch, self.cfg.sandbox, opener=lambda: self.open(task))

    def units(self, kind: str, keys: list[str], work: Callable[[str], dict]) -> dict:
        done = self.ledger.completed(kind)
        todo = [k for k in keys if k not in done]
        failures = 0

        def run(key: str):
            try:
                summary = work(key) or {}
                self.ledger.mark_done(kind, key, **summary)
                return True
            except Exception as exc:  # noqa: BLE001 - record and continue; a re-run retries
                self.ledger.append("unit_error", unit=kind, key=key,
                                   error=f"{type(exc).__name__}: {exc}",
                                   trace=traceback.format_exc()[-3000:])
                return False

        if self.workers <= 1:
            results = [run(k) for k in todo]
        else:
            with ThreadPoolExecutor(self.workers) as pool:
                futures = [pool.submit(run, k) for k in todo]
                results = [f.result() for f in as_completed(futures)]
        failures = results.count(False)
        summary = {"unit": kind, "total": len(keys), "skipped_done": len(keys) - len(todo),
                   "ran": len(todo), "failed": failures}
        self.ledger.append("phase_units", **summary)
        return summary

    def split(self) -> dict[str, str]:
        return read_json(self.dir / "split.json")["tasks"]

    # --- phase 1: prepare ------------------------------------------------------------------
    def prepare(self) -> dict:
        tasks, summary = load_tasks(self.cfg.data)
        write_jsonl(self.path("tasks.jsonl"), [t.model_dump(mode="json") for t in tasks])
        manifest = {**summary, "dataset_sha256": sha256_file(self.cfg.data.dataset_path),
                    "config_sha256": self.cfg.digest()}
        atomic_write_json(self.path("tasks_manifest.json"), manifest)
        self._tasks = None
        self.ledger.append("phase", name="prepare", **manifest)
        return manifest

    # --- phase 1b: gold validation ---------------------------------------------------------
    def validate_gold(self) -> dict:
        def work(task_id: str) -> dict:
            task = self.tasks[task_id]
            result = self.grade(task, task.gold_patch)
            self.append("gold.jsonl", {"task_id": task_id, "grade": result.to_json()})
            return {"status": result.status}

        return self.units("gold", sorted(self.tasks), work)

    def gold_valid(self) -> set[str]:
        return {r["task_id"] for r in self.rows("gold.jsonl") if r["grade"]["status"] == "resolved"}

    # --- phase 2: screen -------------------------------------------------------------------
    def _bare_attempt(self, task: Task, seed: int) -> dict:
        sandbox = self.open(task)
        try:
            state = initial_state(task.problem_statement, sandbox.workdir, sandbox)
            agent = Agent(self.backend, sandbox, self.cfg.agent, self.cfg.cost, None, seed)
            with EnergyMeter() as meter:
                result = agent.run(state)
        finally:
            sandbox.close()
        outcome = self.grade(task, result.final_diff)
        # Full transcript for diagnosis (format errors, tool misuse). Never read by any phase.
        atomic_write_json(self.path("traces", f"{task.instance_id}__{seed}.json"),
                          {"termination": result.termination, "messages": result.state.messages})
        return {
            "task_id": task.instance_id, "repo": task.repo, "seed": seed,
            "termination": result.termination, "credits": result.credits,
            "steps": result.state.step, "wall_seconds": result.state.wall_seconds,
            "tokens": result.state.prompt_tokens + result.state.completion_tokens,
            "energy_wh": meter.watt_hours, "diff": result.final_diff, "grade": outcome.to_json(),
        }

    def screen(self) -> dict:
        valid = self.gold_valid()
        keys = [f"{t}|{s}" for t in sorted(valid) for s in self.cfg.screen.seeds]

        def work(key: str) -> dict:
            task_id, seed = key.rsplit("|", 1)
            row = self._bare_attempt(self.tasks[task_id], int(seed))
            self.append("screen.jsonl", row)
            return {"status": row["grade"]["status"]}

        return self.units("screen", keys, work)

    def zpd_tasks(self) -> dict[str, int]:
        by_task: dict[str, list[dict]] = {}
        for row in self.rows("screen.jsonl"):
            by_task.setdefault(row["task_id"], []).append(row)
        seeds = set(self.cfg.screen.seeds)
        keep = {}
        for task_id, rows in by_task.items():
            if {r["seed"] for r in rows} != seeds:
                continue
            if any(r["grade"]["status"] not in ("resolved", "unresolved") for r in rows):
                continue
            wins = sum(r["grade"]["status"] == "resolved" for r in rows)
            if self.cfg.screen.min_successes <= wins <= self.cfg.screen.max_successes:
                keep[task_id] = wins
        return keep

    # --- phase 3: split --------------------------------------------------------------------
    def make_split(self, reuse_from: str | None = None) -> dict:
        zpd = self.zpd_tasks()
        if reuse_from:
            source = read_json(Path(reuse_from))
            repo_split = source["repositories"]
        else:
            counts: dict[str, int] = {}
            for task_id in zpd:
                repo = self.tasks[task_id].repo
                counts[repo] = counts.get(repo, 0) + 1
            repo_split = split_by_repository(counts, self.cfg.split)
        tasks = {t: repo_split[self.tasks[t].repo] for t in sorted(zpd)
                 if self.tasks[t].repo in repo_split}
        summary = {s: sum(1 for v in tasks.values() if v == s) for s in ("train", "dev", "confirm")}
        atomic_write_json(self.path("split.json"), {
            "repositories": repo_split, "tasks": tasks, "screen_successes": zpd,
            "counts": summary, "reused_from": reuse_from,
        })
        self.ledger.append("phase", name="split", **summary)
        return summary

    # --- phase 4: collect ------------------------------------------------------------------
    def _export(self, task: Task, seed: int, sandbox: Sandbox, harness: EvidenceHarness,
                before: AgentState, view: CheckpointState, prefix: str,
                snapshot_id: str) -> dict:
        key = f"{task.instance_id}__{seed}__{view.index}"
        export = {
            "checkpoint_key": key, "task_id": task.instance_id, "repo": task.repo, "seed": seed,
            "index": view.index, "step": view.step, "tree_hash": view.tree_hash,
            "environment_hash": sandbox.environment_hash, "diff": view.diff,
            "messages": view.messages, "remaining_credits": view.remaining_credits,
            "recent_logprobs": view.recent_logprobs,
            "items": [i.model_dump(mode="json") for i in harness.last_items],
            "producer_credits": harness.last_producer_credits,
            "producer_errors": harness.producer_errors[-10:],
            "snapshot_id": snapshot_id, "agent_state": before.to_json(),
        }
        atomic_write_json(self.path(prefix, f"{key}.json"), export)
        return export

    def _harness(self, task: Task, sandbox: Sandbox, policy: Policy, seed: int,
                 preset=None) -> EvidenceHarness:
        producers = Producers(sandbox, self.backend, self.cfg.evidence, self.cfg.cost)
        return EvidenceHarness(
            producers, policy, task.instance_id, task.problem_statement,
            sandbox.environment_hash, self.cfg.evidence, self.cfg.cost,
            self.cfg.agent.credit_cap, self.count_tokens, seed, preset=preset,
        )

    def collect(self) -> dict:
        split = self.split()
        keys = [f"{t}|{s}" for t, part in sorted(split.items()) if part in ("train", "dev")
                for s in self.cfg.collect_seeds]

        def work(key: str) -> dict:
            task_id, seed_text = key.rsplit("|", 1)
            task, seed = self.tasks[task_id], int(seed_text)
            sandbox = self.open(task)
            exported: list[str] = []
            try:
                harness = self._harness(task, sandbox, NonePolicy(), seed)

                snapshots: list[str] = []

                def pre_checkpoint(_view):
                    snapshots.append(sandbox.snapshot())

                def on_checkpoint(before, view, _packet):
                    export = self._export(task, seed, sandbox, harness, before, view,
                                          "checkpoints", snapshots[-1])
                    exported.append(export["checkpoint_key"])

                state = initial_state(task.problem_statement, sandbox.workdir, sandbox)
                agent = Agent(self.backend, sandbox, self.cfg.agent, self.cfg.cost, harness,
                              seed, on_checkpoint, pre_checkpoint)
                result = agent.run(state)
            finally:
                sandbox.close()
            outcome = self.grade(task, result.final_diff)
            self.append("collect.jsonl", {
                "task_id": task_id, "repo": task.repo, "seed": seed, "split": split[task_id],
                "termination": result.termination, "credits": result.credits,
                "checkpoints": exported, "diff": result.final_diff, "grade": outcome.to_json(),
            })
            return {"checkpoints": len(exported), "status": outcome.status}

        return self.units("collect", keys, work)

    # --- phase 5: labels, features, bug discrimination ---------------------------------------
    def reference_patches(self, task: Task) -> dict[str, str]:
        refs = {"gold": task.gold_patch}
        if self.cfg.label.reference_set == "all_passing":
            for name in ("screen.jsonl", "collect.jsonl"):
                for row in self.rows(name):
                    if row["task_id"] == task.instance_id and row["grade"]["status"] == "resolved":
                        if source_paths(row["diff"]):
                            refs[f"rollout:{sha256_text(row['diff'])[:12]}"] = row["diff"]
        return refs

    def base_files(self, task: Task, refs: dict[str, str]) -> dict[str, str | None]:
        path = self.dir / "base_files" / f"{task.instance_id}.json"
        paths = sorted({p for patch in refs.values() for p in source_paths(patch)})
        if path.exists():
            cached = read_json(path)
            if sorted(cached) == paths:
                return cached
        sandbox = self.open(task)
        try:
            files = read_base_files(sandbox, paths)
        finally:
            sandbox.close()
        atomic_write_json(self.path("base_files", f"{task.instance_id}.json"), files)
        return files

    def checkpoint_keys(self, splits: tuple[str, ...] = ("train", "dev"),
                        prefix: str = "checkpoints") -> list[str]:
        split = self.split()
        folder = self.dir / prefix
        if not folder.exists():
            return []
        keys = []
        for path in sorted(folder.glob("*.json")):
            task_id = path.stem.rsplit("__", 2)[0]
            if split.get(task_id) in splits:
                keys.append(path.stem)
        return keys

    def label(self) -> dict:
        def work(key: str) -> dict:
            export = read_json(self.dir / "checkpoints" / f"{key}.json")
            task = self.tasks[export["task_id"]]
            if not export["items"]:
                result = {"checkpoint_key": key, "families": [], "references": [], "rows": [],
                          "items": [], "summary": None, "note": "no evidence items"}
            else:
                refs_patches = self.reference_patches(task)
                base = self.base_files(task, refs_patches)
                refs = build_references(base, export["diff"], refs_patches,
                                        self.cfg.label.reference_format)
                if not refs:
                    raise RuntimeError("no reference could be built for this checkpoint")
                result = label_checkpoint(
                    self.backend, export, refs, self.cfg.evidence.packet_token_cap,
                    self.count_tokens, self.cfg.label.normalize_per_token,
                    self.cfg.label.item_level,
                )
            atomic_write_json(self.path("labels", f"{key}.json"), result)
            self._features(export)
            return {"families": len(result["families"]), "references": len(result["references"])}

        summary = self.units("label", self.checkpoint_keys(), work)
        self._bsg()
        return summary

    def _view(self, export: dict) -> CheckpointState:
        return CheckpointState(
            index=export["index"], step=export["step"], tree_hash=export["tree_hash"],
            diff=export["diff"], messages=export["messages"],
            remaining_credits=export["remaining_credits"],
            recent_logprobs=export["recent_logprobs"],
        )

    def _features(self, export: dict) -> None:
        items = [EvidenceItem.model_validate(i) for i in export["items"]]
        view = self._view(export)
        hidden = None
        if items:
            hidden, _ = hidden_features(self.backend, view, items,
                                        self.cfg.evidence.packet_token_cap, self.count_tokens)
        records = [feature_record(item, view, len(items), self.cfg.agent.credit_cap,
                                  self.count_tokens, hidden[k] if hidden else None)
                   for k, item in enumerate(items)]
        have_hidden = bool(records) and all(r["hidden"] is not None for r in records)
        np.savez_compressed(
            self.path("features", f"{export['checkpoint_key']}.npz"),
            ids=np.asarray([i.evidence_id for i in items], dtype=str),
            item=np.asarray([r["item"] for r in records], dtype=np.float32),
            state=np.asarray([r["state"] for r in records], dtype=np.float32),
            logprob=np.asarray([r["logprob"] for r in records], dtype=np.float32),
            hidden=np.asarray([r["hidden"] for r in records], dtype=np.float32)
            if have_hidden else np.zeros((0, 0), dtype=np.float32),
        )

    def _bsg(self) -> None:
        by_task: dict[str, list[dict]] = {}
        for key in self.checkpoint_keys():
            export = read_json(self.dir / "checkpoints" / f"{key}.json")
            by_task.setdefault(export["task_id"], []).extend(export["items"])

        def work(task_id: str) -> dict:
            items = by_task[task_id]
            tests = sorted({t for i in items if i["basis"] == "observed" for t in i["tests"]})
            task = self.tasks[task_id]
            outcomes = discriminative_map(task, tests, lambda: self.open(task),
                                          self.cfg.evidence.test_timeout_seconds)
            labels = {i["evidence_id"]: label_item(i, outcomes) for i in items}
            atomic_write_json(self.path("bsg", f"{task_id}.json"), labels)
            return {"items": len(labels)}

        self.units("bsg", sorted(by_task), work)

    # --- phase 6: causal validation (AEV_RO) -------------------------------------------------
    def _labelled_items(self, key: str) -> list[dict]:
        path = self.dir / "labels" / f"{key}.json"
        if not path.exists():
            return []
        return [r for r in read_json(path)["items"] if r["aev_single"] is not None]

    def validation_plan(self) -> list[dict]:
        candidates = []
        for key in self.checkpoint_keys():
            items = self._labelled_items(key)
            if len(items) >= 2:
                ranked = sorted(items, key=lambda r: r["aev_single"])
                candidates.append({"key": key, "top": ranked[-1], "bottom": ranked[0]})
        candidates.sort(key=lambda c: c["top"]["aev_single"])
        n = min(self.cfg.validate_.n_checkpoints, len(candidates))
        if n == 0:
            return []
        bins = np.array_split(np.arange(len(candidates)), 5)
        chosen: list[dict] = []
        per_bin = [n // 5 + (1 if i < n % 5 else 0) for i in range(5)]
        for size, members in zip(per_bin, bins):
            members = sorted(members, key=lambda i: stable_unit_interval("validate",
                                                                         candidates[i]["key"]))
            chosen += [candidates[i] for i in members[:size]]
        return chosen

    def _branch(self, export: dict, policy: Policy, seed: int) -> tuple[dict, Grade]:
        task = self.tasks[export["task_id"]]
        sandbox = restore_sandbox(self.cfg.sandbox, task.image, export["snapshot_id"])
        try:
            items = [EvidenceItem.model_validate(i) for i in export["items"]]
            preset = (export["tree_hash"], items, export["producer_credits"])
            harness = self._harness(task, sandbox, policy, seed, preset=preset)
            state = AgentState.from_json(export["agent_state"])
            if sandbox.tree_hash() != export["tree_hash"]:
                raise RuntimeError("restore fidelity check failed: tree hash differs")
            agent = Agent(self.backend, sandbox, self.cfg.agent, self.cfg.cost, harness, seed)
            with EnergyMeter() as meter:
                agent.deliver_pending_checkpoint(state)
                result = agent.run(state)
        finally:
            sandbox.close()
        outcome = self.grade(task, result.final_diff)
        row = {
            "task_id": task.instance_id, "repo": task.repo,
            "checkpoint_key": export["checkpoint_key"], "seed": seed,
            "termination": result.termination, "credits": result.credits,
            "tokens": result.state.prompt_tokens + result.state.completion_tokens,
            "wall_seconds": result.state.wall_seconds, "energy_wh": meter.watt_hours,
            "events": result.state.events, "diff": result.final_diff,
            "grade": outcome.to_json(),
        }
        return row, outcome

    def validate(self) -> dict:
        plan = self.validation_plan()
        atomic_write_json(self.path("validate_plan.json"), plan)
        arms = {"NONE": lambda c: [], "TOP": lambda c: [c["top"]["evidence_id"]],
                "BOTTOM": lambda c: [c["bottom"]["evidence_id"]], "ALL": None}
        by_key = {c["key"]: c for c in plan}
        keys = [f"{c['key']}|{arm}|{j}" for c in plan for arm in arms
                for j in range(self.cfg.validate_.seeds_per_arm)]

        def work(unit: str) -> dict:
            key, arm, j = unit.split("|")
            export = read_json(self.dir / "checkpoints" / f"{key}.json")
            if arm == "ALL":
                ids = [i["evidence_id"] for i in export["items"]]
            else:
                ids = arms[arm](by_key[key])
            row, outcome = self._branch(export, FixedThenNone(ids),
                                        self.cfg.validate_.seed_base + int(j))
            row.update({"arm": arm, "delivered": ids})
            self.append("validate.jsonl", row)
            return {"status": outcome.status}

        return self.units("validate", keys, work)

    # --- phase 7: train ---------------------------------------------------------------------
    def dataset(self, splits=("train", "dev")) -> dict:
        records, values, repos, checkpoints, tasks, families, ids = [], [], [], [], [], [], []
        for key in self.checkpoint_keys(splits):
            feature_path = self.dir / "features" / f"{key}.npz"
            labels = {r["evidence_id"]: r for r in self._labelled_items(key)}
            if not feature_path.exists() or not labels:
                continue
            data = np.load(feature_path)
            has_hidden = data["hidden"].size > 0
            task_id = key.rsplit("__", 2)[0]
            for k, evidence_id in enumerate(data["ids"].tolist()):
                if evidence_id not in labels:
                    continue
                records.append({
                    "item": data["item"][k].tolist(), "state": data["state"][k].tolist(),
                    "logprob": data["logprob"][k].tolist(),
                    "hidden": data["hidden"][k].tolist() if has_hidden else None,
                })
                values.append(labels[evidence_id]["aev_single"])
                repos.append(self.tasks[task_id].repo)
                checkpoints.append(key)
                tasks.append(task_id)
                families.append(labels[evidence_id]["family"])
                ids.append(evidence_id)
        return {"records": records, "values": np.asarray(values, dtype=float), "repos": repos,
                "checkpoints": checkpoints, "tasks": tasks, "families": families, "ids": ids}

    def redundancy_lambda(self) -> float:
        ratios = []
        for key in self.checkpoint_keys():
            path = self.dir / "labels" / f"{key}.json"
            if not path.exists():
                continue
            label = read_json(path)
            if label.get("summary") and len(label["families"]) > 1:
                ratios.append(label["summary"]["interaction"] / (len(label["families"]) - 1))
        return max(0.0, -float(np.mean(ratios))) if ratios else 0.0

    def train(self) -> dict:
        data = self.dataset()
        if not data["records"]:
            raise RuntimeError("no labelled items with features; run `veritas label` first")
        cfg = self.cfg.probe
        has_hidden = all(r["hidden"] is not None for r in data["records"])
        report = {"n_items": len(data["records"]), "n_repositories": len(set(data["repos"])),
                  "cv": [], "skipped": []}
        oof: dict[tuple[str, str], np.ndarray] = {}
        oof_value: dict[tuple[str, str], np.ndarray] = {}
        combos = {(m, f) for m in cfg.models for f in cfg.feature_sets}
        combos |= {(cfg.gate_model, cfg.gate_features), (cfg.maniple_model, cfg.maniple_features)}
        for model, feature_set in sorted(combos):
            if not has_hidden and feature_set in ("hidden", "full", "full_no_state"):
                report["skipped"].append([model, feature_set, "no hidden features"])
                continue
            try:
                result = cross_validate(data["records"], data["values"], data["repos"],
                                        data["checkpoints"], model, feature_set, cfg.folds,
                                        cfg.positive_threshold, cfg.random_state)
            except ValueError as exc:
                report["skipped"].append([model, feature_set, str(exc)])
                continue
            oof[(model, feature_set)] = result.oof_proba
            oof_value[(model, feature_set)] = result.oof_value
            report["cv"].append({"model": model, "feature_set": feature_set, **result.metrics})
        report["baselines"] = self._baselines(data)
        artifacts = {}
        for name, model, feature_set in (("gate", cfg.gate_model, cfg.gate_features),
                                         ("maniple", cfg.maniple_model, cfg.maniple_features)):
            if (model, feature_set) not in oof:
                report["skipped"].append([name, feature_set, "no CV result; artifact not built"])
                continue
            path = self.path("artifacts", f"{name}.joblib")
            sha = fit_artifact(data["records"], data["values"], model, feature_set,
                               cfg.positive_threshold, cfg.random_state,
                               self.redundancy_lambda(), oof[(model, feature_set)], path)
            artifacts[name] = {"path": str(path), "sha256": sha, "model": model,
                               "feature_set": feature_set}
        linucb_path = self.path("artifacts", "linucb.json")
        self._fit_linucb().save(linucb_path)
        artifacts["linucb"] = {"path": str(linucb_path), "sha256": sha256_file(linucb_path)}
        report["artifacts"] = artifacts
        report["redundancy_lambda"] = self.redundancy_lambda()
        report["gate_threshold"] = self.cfg.confirm.gate_threshold
        report["tau_sensitivity"] = self._tau_sensitivity(data, oof_value)
        atomic_write_json(self.path("train", "report.json"), report)
        self.ledger.append("phase", name="train", artifacts=artifacts)
        return report

    def _baselines(self, data: dict) -> dict:
        """R8 sanity checks: shuffled labels, and task difficulty (screen pass rate) alone."""
        out = {}
        zpd = read_json(self.dir / "split.json")["screen_successes"]
        n_seeds = len(self.cfg.screen.seeds)
        difficulty = [{"item": [zpd.get(t, 0) / n_seeds], "state": [], "logprob": [],
                       "hidden": None} for t in data["tasks"]]
        try:
            out["difficulty_only"] = cross_validate(
                difficulty, data["values"], data["repos"], data["checkpoints"], "logistic",
                "item", self.cfg.probe.folds, self.cfg.probe.positive_threshold, 0).metrics
        except ValueError as exc:
            out["difficulty_only"] = {"error": str(exc)}
        shuffled = np.random.default_rng(0).permutation(data["values"])
        try:
            out["shuffled_labels"] = cross_validate(
                data["records"], shuffled, data["repos"], data["checkpoints"], "logistic",
                "item_state", self.cfg.probe.folds, self.cfg.probe.positive_threshold, 0).metrics
        except ValueError as exc:
            out["shuffled_labels"] = {"error": str(exc)}
        return out

    def _tau_sensitivity(self, data: dict, oof_value: dict) -> list[dict]:
        """G5 (offline): out-of-fold, the items whose predicted value exceeds tau (the GATE rule,
        ignoring redundancy) and the mean of their labelled single-item AEV."""
        key = (self.cfg.probe.gate_model, self.cfg.probe.gate_features)
        if key not in oof_value:
            return []
        predicted = oof_value[key]
        rows = []
        for tau in self.cfg.probe.tau_grid:
            chosen = [v for v, p in zip(data["values"], predicted) if np.isfinite(p) and p > tau]
            rows.append({"tau": tau, "n_delivered": len(chosen),
                         "mean_value_delivered": float(np.mean(chosen)) if chosen else None,
                         "share_delivered": len(chosen) / len(predicted) if len(predicted)
                         else None})
        return rows

    def _fit_linucb(self) -> LinUCB:
        actions = list(LINUCB_ACTIONS)
        model: LinUCB | None = None
        for key in self.checkpoint_keys(("train",)):
            path = self.dir / "labels" / f"{key}.json"
            if not path.exists():
                continue
            label = read_json(path)
            if not label.get("summary"):
                continue
            export = read_json(self.dir / "checkpoints" / f"{key}.json")
            items = [EvidenceItem.model_validate(i) for i in export["items"]]
            x = linucb_context(self._view(export), items, self.cfg.agent.credit_cap)
            if model is None:
                model = LinUCB(actions, len(x))
            values = {tuple(r["key"]): r["aev_ll"] for r in label["rows"]
                      if r["kind"] == "family_subset"}
            present = set(label["families"])
            for action, fams in LINUCB_ACTIONS.items():
                subset = tuple(sorted(present & set(fams)))
                if subset in values and values[subset] is not None:
                    model.update(action, x, values[subset])
        if model is None:
            raise RuntimeError("no labelled training checkpoints for LinUCB")
        return model

    # --- phase 9: confirmation ---------------------------------------------------------------
    def _artifacts(self) -> dict:
        return read_json(self.dir / "train" / "report.json")["artifacts"]

    def _donors(self) -> list[EvidenceItem]:
        donors = []
        for key in self.checkpoint_keys(("train",)):
            export = read_json(self.dir / "checkpoints" / f"{key}.json")
            donors += [EvidenceItem.model_validate(i) for i in export["items"]]
        return donors

    def _oracle(self, task: Task) -> Callable:
        refs_patches = self.reference_patches(task)
        base = self.base_files(task, refs_patches)

        def oracle(state: CheckpointState, items: list[EvidenceItem]):
            refs = build_references(base, state.diff, refs_patches,
                                    self.cfg.label.reference_format)
            if not refs or not items:
                return [], 0.0
            export = {"checkpoint_key": "oracle", "index": state.index,
                      "messages": state.messages,
                      "items": [i.model_dump(mode="json") for i in items]}
            result = label_checkpoint(self.backend, export, refs,
                                      self.cfg.evidence.packet_token_cap, self.count_tokens,
                                      self.cfg.label.normalize_per_token, item_level=False)
            values = {tuple(r["key"]): r["aev_ll"] for r in result["rows"]
                      if r["kind"] == "family_subset" and r["aev_ll"] is not None}
            if not values:
                return [], 0.0
            best = max(values, key=lambda subset: (values[subset], -len(subset)))
            return list(best), 0.0

        return oracle

    def make_policy(self, arm: str, task: Task) -> Policy:
        art = self._artifacts() if arm in ("GATE", "MANIPLE", "LINUCB", "RANDOM_SAME_SIZE") else {}
        if arm == "NONE":
            return NonePolicy()
        if arm == "ALL":
            return AllPolicy()
        if arm == "FIX":
            return FixPolicy()
        if arm == "MANIPLE":
            return ManiplePolicy(Predictor(art["maniple"]["path"], art["maniple"]["sha256"]))
        if arm in ("GATE", "RANDOM_SAME_SIZE"):
            gate = GatePolicy(Predictor(art["gate"]["path"], art["gate"]["sha256"]),
                              self.backend, self.cfg.confirm.gate_threshold)
            return gate if arm == "GATE" else RandomSameSizePolicy(gate)
        if arm == "LINUCB":
            if sha256_file(art["linucb"]["path"]) != art["linucb"]["sha256"]:
                raise ValueError("LinUCB artifact hash mismatch")
            return LinUCBPolicy(LinUCB.load(art["linucb"]["path"]))
        if arm == "QUALITY":
            return QualityPolicy(self.backend, self.cfg.confirm.quality_threshold,
                                 task.problem_statement, self.cfg.evidence.producer_max_new_tokens)
        if arm == "SHUFFLED":
            return ShuffledPolicy(self._donors())
        if arm == "ORACLE":
            return OraclePolicy(self._oracle(task))
        raise ValueError(f"no policy for arm {arm}")

    def parents(self) -> dict:
        split = self.split()
        keys = [f"{t}|{s}" for t, part in sorted(split.items()) if part == "confirm"
                for s in self.cfg.confirm.seeds]

        def work(key: str) -> dict:
            task_id, seed_text = key.rsplit("|", 1)
            task, seed = self.tasks[task_id], int(seed_text)
            sandbox = self.open(task)
            export: dict | None = None
            try:
                harness = self._harness(task, sandbox, NonePolicy(), seed)

                snapshots: list[str] = []

                def pre_checkpoint(_view):
                    snapshots.append(sandbox.snapshot())

                def on_checkpoint(before, view, _packet):
                    nonlocal export
                    export = self._export(task, seed, sandbox, harness, before, view, "parents",
                                          snapshots[-1])
                    raise StopAtCheckpoint()

                state = initial_state(task.problem_statement, sandbox.workdir, sandbox)
                agent = Agent(self.backend, sandbox, self.cfg.agent, self.cfg.cost, harness,
                              seed, on_checkpoint, pre_checkpoint)
                try:
                    result = agent.run(state)
                    final_diff = result.final_diff
                except StopAtCheckpoint:
                    final_diff = None
            finally:
                sandbox.close()
            if export is not None:
                parent_grade = self.grade(task, export["diff"])
                row = {"task_id": task_id, "repo": task.repo, "seed": seed,
                       "has_checkpoint": True, "checkpoint_key": export["checkpoint_key"],
                       "parent_grade": parent_grade.to_json()}
            else:
                parent_grade = self.grade(task, final_diff or "")
                row = {"task_id": task_id, "repo": task.repo, "seed": seed,
                       "has_checkpoint": False, "checkpoint_key": None,
                       "parent_grade": parent_grade.to_json(), "final_diff": final_diff}
            self.append("parents.jsonl", row)
            return {"has_checkpoint": row["has_checkpoint"], "status": parent_grade.status}

        return self.units("parents", keys, work)

    def confirm(self) -> dict:
        parents = [p for p in self.rows("parents.jsonl") if p["has_checkpoint"]]
        keys = [f"{p['checkpoint_key']}|{arm}" for p in parents for arm in self.cfg.confirm.arms]
        parent_by_key = {p["checkpoint_key"]: p for p in parents}

        def work(unit: str) -> dict:
            key, arm = unit.split("|")
            parent = parent_by_key[key]
            task = self.tasks[parent["task_id"]]
            branch_seed = 7919 * parent["seed"] + 1
            if arm == "RESAMPLE":
                row = self._bare_attempt_with_harness(task, branch_seed)
            else:
                export = read_json(self.dir / "parents" / f"{key}.json")
                row, _ = self._branch(export, self.make_policy(arm, task), branch_seed)
            row.update({"arm": arm, "checkpoint_key": key,
                        "parent_status": parent["parent_grade"]["status"]})
            self.append("confirm.jsonl", row)
            return {"status": row["grade"]["status"]}

        return self.units("confirm", keys, work)

    def _bare_attempt_with_harness(self, task: Task, seed: int) -> dict:
        """RESAMPLE: a fresh attempt from the clean checkout under the NONE harness."""
        sandbox = self.open(task)
        try:
            harness = self._harness(task, sandbox, NonePolicy(), seed)
            state = initial_state(task.problem_statement, sandbox.workdir, sandbox)
            agent = Agent(self.backend, sandbox, self.cfg.agent, self.cfg.cost, harness, seed)
            with EnergyMeter() as meter:
                result = agent.run(state)
        finally:
            sandbox.close()
        outcome = self.grade(task, result.final_diff)
        return {
            "task_id": task.instance_id, "repo": task.repo, "seed": seed,
            "termination": result.termination, "credits": result.credits,
            "tokens": result.state.prompt_tokens + result.state.completion_tokens,
            "wall_seconds": result.state.wall_seconds, "energy_wh": meter.watt_hours,
            "events": result.state.events, "diff": result.final_diff,
            "grade": outcome.to_json(),
        }


    # --- H1c: score another actor's checkpoints with this study's model ---------------------
    def cross_label(self, source_dir: str) -> dict:
        source = Path(source_dir)
        src_cfg = StudyConfig.model_validate(read_json(source / "config.json")["config"])
        src_cfg = src_cfg.model_copy(update={"root": str(source.parent)})
        src = Study(src_cfg, backend=self.backend)
        src.count_tokens = self.count_tokens  # packets as *this* actor's tokenizer caps them

        def work(key: str) -> dict:
            export = read_json(source / "checkpoints" / f"{key}.json")
            if not export["items"]:
                return {"skipped": "no items"}
            task = src.tasks[export["task_id"]]
            patches = src.reference_patches(task)
            refs = build_references(src.base_files(task, patches), export["diff"], patches,
                                    self.cfg.label.reference_format)
            if not refs:
                raise RuntimeError("no reference could be built for this checkpoint")
            result = label_checkpoint(self.backend, export, refs,
                                      self.cfg.evidence.packet_token_cap, self.count_tokens,
                                      self.cfg.label.normalize_per_token, True)
            atomic_write_json(self.path("cross_labels", src_cfg.study_id, f"{key}.json"), result)
            return {"references": len(refs)}

        return self.units(f"cross_label:{src_cfg.study_id}", src.checkpoint_keys(), work)


def load_study(config_path: str, workers: int = 1, backend: Backend | None = None) -> Study:
    from .config import load_config

    return Study(load_config(config_path), backend=backend, workers=workers)
