"""Evidence-backed cohort preparation; does not execute or grade agent runs."""

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from .config import load_config
from .data import load_tasks
from .dependency_scope import screen_row
from .io import digest, file_hash, read_jsonl, write_json, write_jsonl
from .schema import StrictModel

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SHA256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Commit = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]


class Evidence(StrictModel):
    kind: Literal["issue", "base_code"]
    quote: Text
    path: str | None = None
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    base_commit: Commit | None = None
    file_sha256: SHA256 | None = None

    @model_validator(mode="after")
    def locator(self):
        fields = (self.path, self.start_line, self.end_line, self.base_commit, self.file_sha256)
        if self.kind == "issue":
            if any(value is not None for value in fields):
                raise ValueError("Issue evidence must not contain a code locator")
        else:
            if any(value is None for value in fields):
                raise ValueError("Base-code evidence requires path, lines, commit, and file hash")
            path = PurePosixPath(self.path)
            if (not self.path or path.is_absolute() or ".." in path.parts
                    or "\\" in self.path or ":" in self.path or path.suffix != ".py"):
                raise ValueError("Base-code evidence requires a relative Python file path")
            if self.end_line < self.start_line:
                raise ValueError("Evidence line range is reversed")
        return self


class Review(StrictModel):
    reviewer: Text
    status: Literal["include", "exclude", "uncertain"]
    reason: Text
    public_evidence: list[Evidence] = Field(min_length=1)
    target_symbol: Text | None = None
    target_evidence: Evidence | None = None
    caller_symbol: Text | None = None
    caller_evidence: Evidence | None = None
    independent_and_outcome_blind: Literal[True]

    @model_validator(mode="after")
    def included_target(self):
        if self.status == "include":
            if not self.target_symbol or not self.caller_symbol:
                raise ValueError("Included tasks require target and caller symbols")
            if any(e is None or e.kind != "base_code"
                   for e in (self.target_evidence, self.caller_evidence)):
                raise ValueError("Included tasks require target and caller base-code evidence")
        return self


class Annotation(StrictModel):
    task_id: Text
    group_id: Text
    public_task_sha256: SHA256
    reviews: list[Review] = Field(min_length=2, max_length=2)
    adjudication: Review | None = None

    @model_validator(mode="after")
    def reviewers(self):
        people = [r.reviewer.casefold() for r in self.reviews]
        if self.adjudication:
            people.append(self.adjudication.reviewer.casefold())
        if len(people) != len(set(people)):
            raise ValueError("Two distinct reviewers and a distinct adjudicator are required")
        # Disagreement about the target matters even if both say include.
        def decision(r):
            if r.status != "include":
                return (r.status,)
            return (r.status, r.target_symbol, r.target_evidence.path,
                    r.caller_symbol, r.caller_evidence.path)
        if decision(self.reviews[0]) != decision(self.reviews[1]) and not self.adjudication:
            raise ValueError("Review disagreement requires adjudication")
        return self

    @property
    def resolved(self):
        return self.adjudication or self.reviews[0]


class Protocol(StrictModel):
    schema_version: Literal[1]
    family: Literal["python_function_interface_and_callers"]
    selection_rule: Literal["all_reviewed_includes"]
    endpoint: Literal["independent_swe_task_success"]
    arms: tuple[Literal["00"], Literal["10"], Literal["01"], Literal["11"]]
    actor_identity: Text
    verifier_identity: Text
    trigger_a: Text
    trigger_b: Text
    feedback_and_repair: Text
    missing_trigger_policy: Literal["retain_assigned_arm_without_forced_check"]
    failure_policy: Literal["retain_all_attempts_report_infrastructure_separately"]
    grading_protocol: Text
    meaningful_effect: float = Field(gt=0, le=1)
    repetitions: int = Field(gt=0)
    seeds: list[int] = Field(min_length=1)
    confirmation_fraction: float = Field(gt=0, lt=1)
    partition_seed: int
    partition_unit: Literal["group", "repository"]
    max_steps: int = Field(gt=0)
    verification_budget: float = Field(gt=0)
    verification_cost: float = Field(gt=0)
    budget_unit: Literal["verifier_call_credit"]
    outcome_blind_freeze: Literal[True]

    @model_validator(mode="after")
    def repeated_seeds(self):
        if len(self.seeds) != self.repetitions or len(set(self.seeds)) != self.repetitions:
            raise ValueError("Provide one distinct seed per repetition")
        if Decimal(str(self.verification_budget)) < 2 * Decimal(str(self.verification_cost)):
            raise ValueError("Four-arm pilot requires an affordable two-check arm")
        return self


def verified_scope(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("status") != "awaiting_independent_scope_review":
        raise ValueError("Unsupported scope status")
    for name in ("scope.json", "review_queue.jsonl"):
        if file_hash(directory / name) != manifest.get("artifact_hashes", {}).get(name):
            raise ValueError(f"Scope integrity failure: {name}")
    rows = list(read_jsonl(directory / "review_queue.jsonl"))
    if len({r["task_id"] for r in rows}) != len(rows) or len(rows) != manifest["queued_tasks"]:
        raise ValueError("Duplicate or missing scope rows")
    return manifest, rows


def prepare_reviews(scope, output):
    manifest, rows = verified_scope(scope)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_jsonl(output / "annotations.jsonl", ({
        "task_id": r["task_id"], "group_id": r["group_id"],
        "public_task_sha256": r["public_task_sha256"],
        "reviews": [], "adjudication": None,
    } for r in rows))
    write_json(output / "review_binding.json", {
        "scope_manifest_sha256": file_hash(Path(scope) / "manifest.json"),
        "scope_artifact_hashes": manifest["artifact_hashes"],
        "status": "unreviewed_template",
    })
    return {"status": "unreviewed_template", "tasks": len(rows), "output": str(output)}


def validate_evidence(review, row):
    for evidence in [*review.public_evidence, review.target_evidence, review.caller_evidence]:
        if evidence is None:
            continue
        if evidence.kind == "issue" and evidence.quote not in row["prompt"]:
            raise ValueError(f"Issue quote not present in public prompt: {row['task_id']}")
        if evidence.kind == "base_code" and evidence.base_commit != row["base_commit"]:
            raise ValueError(f"Evidence does not reference pinned base commit: {row['task_id']}")


def finalize_cohort(scope, tasks, reviews, protocol, config, output):
    output = Path(output)
    if output.exists():
        raise ValueError("Cohort output already exists; use a new directory")
    manifest, rows = verified_scope(scope)
    for name in ("manifest.json", "tasks.jsonl", "splits.json"):
        if file_hash(Path(tasks) / name) != manifest["input_hashes"][name]:
            raise ValueError(f"Scope input changed: {name}")
    # Rebuild public records from verified task inputs, rather than trusting queue edits.
    expected = [r for t, a in load_tasks(tasks, split="dev", source=manifest["source_filter"])
                if (r := screen_row(t, a)) is not None]
    if sorted(expected, key=lambda r: r["task_id"]) != rows:
        raise ValueError("Scope queue differs from prepared public task evidence")
    annotations = [Annotation.model_validate(r) for r in read_jsonl(reviews)]
    by_id = {a.task_id: a for a in annotations}
    if len(by_id) != len(annotations) or set(by_id) != {r["task_id"] for r in rows}:
        raise ValueError("Annotations must cover every queued task exactly once")
    spec = Protocol.model_validate(json.loads(Path(protocol).read_text()))
    cfg = load_config(config)
    for name in ("max_steps", "verification_budget", "verification_cost", "budget_unit"):
        if getattr(spec, name) != getattr(cfg.run, name):
            raise ValueError(f"Protocol/config mismatch: {name}")
    selected, decisions = [], []
    for row in rows:
        annotation = by_id[row["task_id"]]
        if (annotation.group_id != row["group_id"]
                or annotation.public_task_sha256 != row["public_task_sha256"]):
            raise ValueError(f"Annotation identity mismatch: {row['task_id']}")
        for review in [*annotation.reviews, annotation.adjudication]:
            if review:
                validate_evidence(review, row)
        decisions.append(annotation.model_dump(mode="json"))
        if annotation.resolved.status == "include":
            if not row["repo"] or not row["base_commit"]:
                raise ValueError("Included task lacks pinned repository identity")
            selected.append(row)
    if not selected:
        raise ValueError("No reviewed inclusions; cohort not finalized")
    unit = "repo" if spec.partition_unit == "repository" else "group_id"
    group_repos = {}
    for row in selected:
        if group_repos.setdefault(row["group_id"], row["repo"]) != row["repo"]:
            raise ValueError("One task group maps to conflicting repositories")
    units = sorted({r[unit] for r in selected}, key=lambda u: digest([spec.partition_seed, u]))
    if len(units) < 2:
        raise ValueError("Need at least two partition units for discovery and confirmation")
    n = min(len(units) - 1, max(1, round(len(units) * spec.confirmation_fraction)))
    confirmation = set(units[:n])
    cohort = [{**{k: v for k, v in r.items() if k != "review"},
               "eligibility": by_id[r["task_id"]].resolved.model_dump(mode="json"),
               "research_partition": "confirmation" if r[unit] in confirmation else "discovery"}
              for r in selected]
    output.mkdir(parents=True, exist_ok=False)
    write_jsonl(output / "cohort.jsonl", cohort)
    write_jsonl(output / "reviews.jsonl", decisions)
    write_json(output / "protocol.json", spec.model_dump(mode="json"))
    write_json(output / "runtime_config.json", cfg.model_dump(mode="json"))
    write_json(output / "scope_manifest.json", manifest)
    write_json(output / "scope.json", json.loads((Path(scope) / "scope.json").read_text()))
    result = {
        "schema_version": 1, "status": "reviewed_development_cohort_frozen",
        "inference_started": False, "execution_supported": False,
        "evidence_verification": "issue_quotes_checked_code_locators_reviewer_attested",
        "review_independence": "reviewer_attested_not_machine_proven",
        "included_tasks": len(cohort),
        "decisions": dict(Counter(a.resolved.status for a in annotations)),
        "partitions": dict(Counter(r["research_partition"] for r in cohort)),
        "input_hashes": {"scope_manifest": file_hash(Path(scope) / "manifest.json"),
                         "annotations": file_hash(Path(reviews)),
                         "protocol": file_hash(Path(protocol)), "config": file_hash(Path(config))},
        "artifact_hashes": {name: file_hash(output / name) for name in (
            "cohort.jsonl", "reviews.jsonl", "protocol.json", "runtime_config.json",
            "scope_manifest.json", "scope.json")},
        "implementation_sha256": file_hash(Path(__file__)),
        "runtime_source_hashes": {
            name: file_hash(Path(__file__).with_name(name)) for name in (
                "models.py", "runtime.py", "contracts.py", "verifier.py",
                "graph_verifier.py", "config.py", "sandbox.py", "worker.py")
        },
    }
    write_json(output / "manifest.json", result)
    return result


def verify_cohort(directory):
    """Check local artifact integrity; hashes are not external authenticity proofs."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("status") != "reviewed_development_cohort_frozen":
        raise ValueError("Not a finalized development cohort")
    for name in ("cohort.jsonl", "reviews.jsonl", "protocol.json", "runtime_config.json",
                 "scope_manifest.json", "scope.json"):
        if file_hash(directory / name) != manifest.get("artifact_hashes", {}).get(name):
            raise ValueError(f"Frozen cohort integrity failure: {name}")
    Protocol.model_validate(json.loads((directory / "protocol.json").read_text()))
    return {"status": "local_integrity_verified", "included_tasks": manifest["included_tasks"],
            "execution_supported": False}
