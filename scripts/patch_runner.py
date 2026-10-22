from pathlib import Path

p = Path("src/veritas/feedback_runner.py")
text = p.read_text(encoding="utf-8")

old_setup = """        def setup_container_task(ws: Path) -> tuple[str, str]:
            ws.mkdir(parents=True, exist_ok=True)
            mount_ws = to_container_mount_path(ws)
            run_cmd([
                "docker", "run", "--rm",
                "-v", f"{mount_ws}:/out_ws",
                image_name,
                "sh", "-c", "cp -a . /out_ws/ 2>/dev/null || true"
            ])
            return task.repo or "repo", task.prompt"""

new_setup = """        def setup_container_task(ws: Path) -> tuple[str, str]:
            ws.mkdir(parents=True, exist_ok=True)
            mount_ws = to_container_mount_path(ws)
            inspect_code, _, _ = run_cmd(["docker", "image", "inspect", image_name], timeout=15)
            if inspect_code != 0:
                print(f"    [Docker] Image {image_name} not local; pulling from registry...")
                pull_code, _, pull_err = run_cmd(["docker", "pull", image_name], timeout=900)
                if pull_code != 0:
                    print(f"    [Docker] Warning: Pull returned code {pull_code}: {pull_err[:300]}")
            run_cmd([
                "docker", "run", "--rm",
                "-v", f"{mount_ws}:/out_ws",
                image_name,
                "sh", "-c", "cp -a . /out_ws/ 2>/dev/null || true"
            ], timeout=180)
            return task.repo or "repo", task.prompt"""

assert old_setup in text, "old_setup not found"
text = text.replace(old_setup, new_setup)

old_producer = """def make_evidence_producer(task: Task):
    \"\"\"Factory creating an evidence producer for a repository task.\"\"\"
    def produce(checkpoint: PatchCheckpoint, workspace: Path, record, session) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []

        # 1. Targeted test execution in a disposable copy of workspace
        with tempfile.TemporaryDirectory(prefix="veritas-check-") as tmp:
            tmp_ws = Path(tmp) / "check_ws"
            shutil.copytree(workspace, tmp_ws)
            passed, test_out = evaluate_workspace(tmp_ws)

        if passed:
            items.append(EvidenceItem.create(
                task_id=checkpoint.task_id, branch_id=checkpoint.branch_id,
                checkpoint_id=checkpoint.checkpoint_id, source="test", basis="observed",
                patch_hash=checkpoint.patch_hash, tree_hash=checkpoint.tree_hash,
                environment_hash=checkpoint.environment_hash,
                command="pytest tests/ -q", raw_artifact_hash=digest(test_out),
                claim="All repository unit tests passed successfully.",
                affected_files=checkpoint.changed_files,
                cost_credits=0.5,
            ))
        else:
            lines = test_out.splitlines()
            summary_lines = [l for l in lines if l.startswith("FAILED ") or "AssertionError" in l or "Error:" in l]
            claim = "\\n".join(summary_lines[:3]) or test_out[-500:]

            location = None
            observed = None
            expected = None
            for l in lines:
                if "::" in l and ("FAILED" in l or "ERROR" in l):
                    parts = l.split()
                    for p in parts:
                        if "::" in p:
                            location = p
                            break
                if "assert " in l or "AssertionError" in l:
                    observed = l.strip()
                if "== " in l or "!= " in l:
                    expected = l.strip()

            items.append(EvidenceItem.create(
                task_id=checkpoint.task_id, branch_id=checkpoint.branch_id,
                checkpoint_id=checkpoint.checkpoint_id, source="test", basis="observed",
                patch_hash=checkpoint.patch_hash, tree_hash=checkpoint.tree_hash,
                environment_hash=checkpoint.environment_hash,
                command="pytest tests/ -q", raw_artifact_hash=digest(test_out),
                claim=claim[:1500], location=location, observed=observed,
                expected_if_observed=expected, affected_files=checkpoint.changed_files,
                cost_credits=0.5,
            ))"""

new_producer = """def make_evidence_producer(task: Task, baseline: Path | None = None):
    \"\"\"Factory creating an evidence producer for a repository task.\"\"\"
    def produce(checkpoint: PatchCheckpoint, workspace: Path, record, session) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []

        # 1. Targeted test execution
        cmd_str = "pytest tests/ -q"
        if task.source == "swe_rebench" and task.private.get("image_name"):
            patch = make_patch(baseline, workspace) if (baseline and baseline.exists()) else ""
            res = evaluate_task_in_container(
                image_name=task.private["image_name"],
                patch=patch,
                test_patch=task.private.get("test_patch"),
                test_cmd=task.private.get("test_cmd", "pytest"),
                fail_to_pass=task.private.get("FAIL_TO_PASS", []),
                pass_to_pass=task.private.get("PASS_TO_PASS", []),
                timeout_seconds=90,
            )
            passed = res.get("resolved", False)
            test_out = res.get("log", "")
            cmd_str = task.private.get("test_cmd", "pytest")
        else:
            with tempfile.TemporaryDirectory(prefix="veritas-check-") as tmp:
                tmp_ws = Path(tmp) / "check_ws"
                shutil.copytree(workspace, tmp_ws)
                passed, test_out = evaluate_workspace(tmp_ws)

        if passed:
            items.append(EvidenceItem.create(
                task_id=checkpoint.task_id, branch_id=checkpoint.branch_id,
                checkpoint_id=checkpoint.checkpoint_id, source="test", basis="observed",
                patch_hash=checkpoint.patch_hash, tree_hash=checkpoint.tree_hash,
                environment_hash=checkpoint.environment_hash,
                command=cmd_str, raw_artifact_hash=digest(test_out),
                claim="All repository unit tests passed successfully.",
                affected_files=checkpoint.changed_files,
                cost_credits=0.5,
            ))
        else:
            lines = test_out.splitlines()
            summary_lines = [l for l in lines if l.startswith("FAILED ") or "AssertionError" in l or "Error:" in l or "ERROR " in l]
            claim = "\\n".join(summary_lines[:3]) or test_out[-500:]

            location = None
            observed = None
            expected = None
            for l in lines:
                if "::" in l and ("FAILED" in l or "ERROR" in l):
                    parts = l.split()
                    for p in parts:
                        if "::" in p:
                            location = p
                            break
                elif not location and ("ImportError:" in l or "SyntaxError:" in l or "TypeError:" in l or "AttributeError:" in l):
                    observed = l.strip()
                if "assert " in l or "AssertionError" in l:
                    observed = l.strip()
                if "== " in l or "!= " in l:
                    expected = l.strip()

            items.append(EvidenceItem.create(
                task_id=checkpoint.task_id, branch_id=checkpoint.branch_id,
                checkpoint_id=checkpoint.checkpoint_id, source="test", basis="observed",
                patch_hash=checkpoint.patch_hash, tree_hash=checkpoint.tree_hash,
                environment_hash=checkpoint.environment_hash,
                command=cmd_str, raw_artifact_hash=digest(test_out),
                claim=claim[:1500], location=location, observed=observed,
                expected_if_observed=expected, affected_files=checkpoint.changed_files,
                cost_credits=0.5,
            ))"""

assert old_producer in text, "old_producer not found"
text = text.replace(old_producer, new_producer)

old_call = "evidence_producer = make_evidence_producer(task)"
new_call = "evidence_producer = make_evidence_producer(task, parent_baseline)"
assert old_call in text, "old_call not found"
text = text.replace(old_call, new_call)

p.write_text(text, encoding="utf-8")
print("Updated src/veritas/feedback_runner.py successfully")
