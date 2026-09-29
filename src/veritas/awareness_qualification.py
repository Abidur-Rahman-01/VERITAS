"""Inspect study prerequisites without inference, image pulls, or changing a plan."""

import json
import platform
import tempfile
from pathlib import Path

import httpx

from .awareness import checked_splits, load_protocol_config, plan_study
from .awareness_grading import harness_fingerprint
from .data import load_tasks
from .io import digest, file_hash, write_json
from .sandbox import command, initialize_swe_workspace
from .sanitize import redact
from .state import tree_hash


def qualify_protocol(config, output, *, execute=command, initialize=initialize_swe_workspace,
                     client_factory=httpx.Client):
    spec = load_protocol_config(config)
    report = {"version": 1, "protocol_hash": digest(spec.model_dump(mode="json")),
              "host": {"system": platform.system(), "machine": platform.machine()},
              "checks": {}, "image_digests": {}, "base_tree_hashes": {},
              "model_identities": {}, "inference_exercised": False,
              "grader_exercised": False}
    checks = report["checks"]

    def check(name, operation):
        try:
            result = operation()
            checks[name] = {"ok": True, "result": result}
            return result
        except Exception as exc:
            checks[name] = {"ok": False, "error": redact(f"{type(exc).__name__}: {exc}")}
            return None

    def grader():
        fingerprint = harness_fingerprint(spec.grader.python)
        commit = (fingerprint.get("origin") or {}).get("vcs_info", {}).get("commit_id")
        if spec.source == "swe_rebench" and commit != "d307ff9f2168a0448843c0d5881d2cd498d9f73f":
            raise ValueError("Grader is not the pinned SWE-ReBench fork")
        if spec.grader.package_sha256 not in (None, fingerprint["sha256"]):
            raise ValueError("Grader fingerprint differs from configuration")
        report["grader_package_sha256"] = fingerprint["sha256"]
        return {"commit": commit, "sha256": fingerprint["sha256"]}

    check("grader_package", grader)

    def cohort():
        splits = checked_splits(spec.splits)
        if (splits["parent_manifest_sha256"] != file_hash(Path(spec.tasks) / "manifest.json")
                or splits["source"] != spec.source):
            raise ValueError("Dataset/source does not match frozen repository pools")
        tasks, _ = plan_study(spec, [task for task, _ in load_tasks(spec.tasks)], splits)
        return tasks

    tasks = check("cohort", cohort)
    if tasks is not None:
        checks["cohort"]["result"] = {"tasks": len(tasks), "repositories": len({t.repo for t in tasks})}
    def inspect_docker():
        value = json.loads(execute(["docker", "info", "--format", '{{json .}}'], timeout=20))
        if not value.get("ServerVersion") or value.get("OSType") != "linux":
            raise ValueError("A running Linux Docker engine is required")
        return value

    docker = check("docker", inspect_docker)
    if docker:
        checks["docker"]["result"] = {key: docker.get(key) for key in
                                      ("ServerVersion", "OSType", "Architecture")}
    for actor in [*spec.actors, spec.reviewer]:
        def inspect_model(actor=actor):
            if any(s.startswith("replace-") for s in (actor.revision, actor.family, actor.model.name)):
                raise ValueError("Replace placeholder model family/name/revision")
            cfg = actor.model
            if cfg.backend == "transformers":
                raise ValueError("Qualify local Transformers checkpoint separately")
            headers = {}
            import os

            if os.environ.get(cfg.api_key_env):
                headers["Authorization"] = "Bearer " + os.environ[cfg.api_key_env]
            with client_factory(timeout=min(cfg.timeout_seconds, 20)) as client:
                response = client.get(cfg.base_url.rstrip("/") + (
                    "/api/tags" if cfg.backend == "ollama" else "/models"), headers=headers)
                response.raise_for_status()
                data = response.json()
            if cfg.backend == "ollama":
                matches = [m for m in data.get("models", []) if m.get("name") == cfg.name]
                if len(matches) != 1 or matches[0].get("digest") != actor.revision:
                    raise ValueError("Ollama model digest/name differs from declared revision")
                result = {"name": cfg.name, "revision": actor.revision,
                          "identity_source": "Ollama tag inventory; not signed inference attestation"}
            else:
                if cfg.name not in {m.get("id") for m in data.get("data", [])}:
                    raise ValueError("Configured model not advertised by endpoint")
                result = {"name": cfg.name, "revision": actor.revision,
                          "identity_source": "declared revision; verify during signed inference if enabled"}
            report["model_identities"][actor.id] = result
            return result
        check(f"model/{actor.id}", inspect_model)
    host_arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64",
                 "AMD64": "amd64"}.get(platform.machine(), platform.machine())
    if tasks is not None and docker:
        for task in tasks:
            instance = task.private["instance_id"]
            def inspect_image(task=task, instance=instance):
                image = spec.images[instance]
                info = json.loads(execute(["docker", "image", "inspect", image], timeout=20))[0]
                image_platform = f"{info['Os']}/{info['Architecture']}"
                if image_platform != (spec.sandbox.platform or f"linux/{host_arch}"):
                    raise ValueError("Image platform differs from configured actor platform")
                if image_platform != (spec.grader.platform or f"linux/{host_arch}") or (
                    spec.grader.platform and spec.grader.platform != f"linux/{host_arch}"):
                    raise ValueError("Pinned grader follows host architecture; use a compatible worker")
                if spec.image_digests.get(instance) not in (None, info["Id"]):
                    raise ValueError("Image digest differs from configuration")
                # This actually starts the image and extracts the requested base commit.
                with tempfile.TemporaryDirectory(prefix="veritas-qualify-") as temporary:
                    work = Path(temporary) / "workspace"
                    initialize(info["Id"], work, task.base_commit, spec.sandbox.platform)
                    base = tree_hash(work)
                if spec.base_tree_hashes.get(instance) not in (None, base):
                    raise ValueError("Base tree hash differs from configuration")
                report["image_digests"][instance] = info["Id"]
                report["base_tree_hashes"][instance] = base
                return {"image_id": info["Id"], "platform": image_platform, "base_tree_hash": base}
            check(f"image/{instance}", inspect_image)
    report["prerequisites_ready"] = all(c["ok"] for c in checks.values())
    report["live_validation_required"] = ["actor/reviewer smoke inference", "independent grading smoke",
                                          "blinded development rubric validation"]
    write_json(output, report)
    return report
