"""Independent SWE grading, with evidence from the pinned harness's two report schemas."""

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictBool, model_validator

from .io import digest, file_hash, write_json, write_jsonl
from .sanitize import redact
from .schema import StrictModel


class GradeRecord(StrictModel):
    status: Literal["resolved", "unresolved", "invalid_patch", "ungraded",
                    "infrastructure_error", "timeout", "interrupted"]
    resolved: StrictBool | None = None
    patch_hash: str
    harness_identity: str
    harness_package_sha256: str | None = None
    grading_id: str
    report_hash: str | None = None
    evidence: dict[str, str] = Field(default_factory=dict)
    source: str | None = None
    error: str | None = None
    seconds: float | None = Field(default=None, ge=0)
    prediction_hash: str | None = None
    dataset_hash: str | None = None
    platform: str | None = None

    @model_validator(mode="after")
    def valid_outcome(self):
        expected = {"resolved": True, "unresolved": False, "invalid_patch": False}.get(self.status)
        if self.resolved is not expected:
            raise ValueError("Grader status and resolved flag disagree")
        return self


def harness_fingerprint(python):
    """Read package files without importing or executing the grader environment."""
    executable = Path(python).absolute() if "/" in python else Path(shutil.which(python) or python)
    if not executable.is_file():
        raise ValueError("Configured grader Python does not exist")
    # Do not resolve the venv executable symlink: its parent selects site-packages.
    environment = executable.parent.parent
    # Unix venvs use lib/pythonX/site-packages; Windows venvs use
    # Lib/site-packages. Keep discovery scoped to this interpreter's venv so
    # the dedicated-grader isolation check still rejects ambiguous installs.
    packages = sorted({
        package
        for pattern in ("lib/python*/site-packages/swebench", "Lib/site-packages/swebench")
        for package in environment.glob(pattern)
    })
    if len(packages) != 1:
        raise ValueError("Use a dedicated grader environment containing one swebench package")
    package = packages[0]
    files = {p.relative_to(package).as_posix(): file_hash(p)
             for p in sorted(package.rglob("*.py"))}
    if "harness/run_evaluation.py" not in files or "harness/reporting.py" not in files:
        raise ValueError("Incomplete SWE harness installation")
    direct_urls = sorted(package.parent.glob("swebench-*.dist-info/direct_url.json"))
    origin = json.loads(direct_urls[0].read_text()) if len(direct_urls) == 1 else None
    body = {"files": files, "origin": origin}
    return {**body, "sha256": digest(body)}


def parse_grade(report, instance, detail=None, instance_log=None):
    """Parse pinned schema-v2 run summaries; missing reports never mean test failure."""
    if not isinstance(report, dict) or report.get("schema_version") not in (None, 2):
        raise ValueError("Unsupported SWE report schema")
    statuses = {"resolved_ids": ("resolved", True), "unresolved_ids": ("unresolved", False),
                "empty_patch_ids": ("invalid_patch", False),
                "error_ids": ("infrastructure_error", None), "incomplete_ids": ("ungraded", None)}
    matches = []
    for key, value in statuses.items():
        ids = report.get(key, [])
        if not isinstance(ids, list) or any(not isinstance(x, str) for x in ids):
            raise ValueError("Unsupported SWE report schema")
        if instance in ids:
            matches.append(value)
    if len(matches) > 1:
        raise ValueError("Conflicting SWE grader outcomes")
    status, resolved = matches[0] if matches else ("ungraded", None)
    if detail is not None:
        entry = detail.get(instance)
        if not isinstance(entry, dict) or type(entry.get("resolved")) is not bool:
            raise ValueError("Invalid per-instance SWE report")
        if resolved is not None and entry["resolved"] != resolved:
            raise ValueError("Summary and instance SWE reports disagree")
        if entry.get("patch_is_None") or entry.get("patch_exists") is False:
            status, resolved = "invalid_patch", False
        elif entry.get("patch_successfully_applied") is False:
            # The fork also uses this flag for a failed evaluation log. It does not
            # distinguish an invalid patch from a broken environment by itself.
            status, resolved = "infrastructure_error", None
    if status == "infrastructure_error" and instance_log is not None:
        # The pinned runner emits this marker only after every git-apply attempt
        # failed, before running tests. Other harness errors remain unknown.
        if ">>>>> Patch Apply Failed:" in instance_log:
            status, resolved = "invalid_patch", False
    return {"status": status, "resolved": resolved}


def grade_patch(task, patch, spec, directory, opaque_id, execute=subprocess.run):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    result = GradeRecord(status="ungraded", patch_hash=digest(patch),
                         harness_identity=spec.identity, grading_id=opaque_id,
                         harness_package_sha256=spec.package_sha256, platform=spec.platform)
    if not patch.strip():
        result = result.model_copy(update={"status": "invalid_patch", "resolved": False,
                                           "source": "empty_patch", "seconds": 0.0})
        write_json(directory / "result.json", result.model_dump(mode="json"))
        return result.model_dump(mode="json")
    write_jsonl(directory / "task.jsonl", [task.private])
    write_jsonl(directory / "prediction.jsonl", [{"instance_id": task.private["instance_id"],
        "model_patch": patch, "model_name_or_path": "candidate"}])
    result.prediction_hash = file_hash(directory / "prediction.jsonl")
    result.dataset_hash = file_hash(directory / "task.jsonl")
    python = str(Path(spec.python).absolute()) if "/" in spec.python else spec.python
    argv = [python, "-m", "swebench.harness.run_evaluation", "--dataset_name",
            str(directory / "task.jsonl"), "--predictions_path", str(directory / "prediction.jsonl"),
            "--run_id", opaque_id, "--namespace", spec.namespace, "--max_workers", "1",
            "--timeout", str(max(1, int(spec.timeout_seconds)))]
    write_json(directory / "command.json", {"argv": argv, "harness_identity": spec.identity})
    try:
        actual = harness_fingerprint(spec.python)
        if not spec.package_sha256 or actual["sha256"] != spec.package_sha256:
            raise ValueError("Installed grader differs from the frozen package fingerprint")
        if spec.platform is not None:
            import platform

            host_arch = {"arm64": "aarch64", "AMD64": "x86_64"}.get(platform.machine(), platform.machine())
            expected_arch = {"linux/arm64": "aarch64", "linux/amd64": "x86_64"}.get(spec.platform)
            if expected_arch != host_arch:
                raise ValueError("Pinned harness uses host architecture; configured grader platform differs")
        with (directory / "harness.log").open("w") as log:
            process = execute(argv, cwd=directory, stdout=log, stderr=subprocess.STDOUT,
                              check=False, timeout=spec.timeout_seconds)
        report_path = directory / f"candidate.{opaque_id}.json"
        instance = task.private["instance_id"]
        detail_path = directory / "logs" / "run_evaluation" / opaque_id / "candidate" / instance / "report.json"
        instance_log_path = detail_path.with_name("run_instance.log")
        if not report_path.is_file():
            raise ValueError("SWE report missing; inspect harness.log")
        detail = json.loads(detail_path.read_text()) if detail_path.is_file() else None
        result = result.model_copy(update=parse_grade(json.loads(report_path.read_text()), instance, detail,
            instance_log_path.read_text(errors="replace") if instance_log_path.is_file() else None))
        result.report_hash = file_hash(report_path)
        result.source = "independent_swe_harness"
        if getattr(process, "returncode", 0):
            result.error = f"Harness exited with {process.returncode}; retained explicit report evidence"
    except subprocess.TimeoutExpired:
        result = result.model_copy(update={"status": "timeout", "resolved": None,
                                           "error": "Independent grading deadline exceeded"})
    except Exception as exc:
        result = result.model_copy(update={"status": "infrastructure_error", "resolved": None,
                                           "error": redact(f"{type(exc).__name__}: {exc}")})
    result.seconds = time.monotonic() - start
    result.evidence = {p.relative_to(directory).as_posix(): file_hash(p)
                       for p in sorted(directory.rglob("*")) if p.is_file()
                       and p.suffix in {".json", ".jsonl", ".log", ".txt"}}
    result = GradeRecord.model_validate(result.model_dump(mode="json"))
    write_json(directory / "result.json", result.model_dump(mode="json"))
    return result.model_dump(mode="json")
