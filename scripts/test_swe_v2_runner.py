#!/usr/bin/env python3
"""
Test runner for genuine SWE-rebench-V2 task execution inside Docker sandbox.
"""
import os
import stat
import sys
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from veritas.schema import Task
from veritas.sandbox import make_patch
from veritas.io import read_jsonl
from scripts.veritas_cloud_worker import evaluate_task_in_container, run_cmd, to_container_mount_path

tasks_file = REPO_ROOT / "data" / "v2_cohort_500" / "tasks.jsonl"
first_row = next(iter(read_jsonl(tasks_file)))
task = Task.model_validate(first_row)
print(f"Loaded Task: {task.task_id} (Repo: {task.repo})", flush=True)
print(f"Docker image: {task.private['image_name']}", flush=True)

test_dir = REPO_ROOT / "runs" / "test_v2_block"
test_dir.mkdir(parents=True, exist_ok=True)
baseline = test_dir / "baseline"
workspace = test_dir / "workspace"

def remove_dir(d: Path):
    if d.exists():
        def on_exc(func, path, exc_info):
            os.chmod(path, stat.S_IWRITE)
            func(path)
        shutil.rmtree(d, onerror=on_exc)

remove_dir(baseline)
remove_dir(workspace)
workspace.mkdir(parents=True, exist_ok=True)

# 1. Extract files from container
mount_ws = to_container_mount_path(workspace)
print(f"Extracting repository files into {workspace}...", flush=True)
code, out, err = run_cmd([
    "docker", "run", "--rm",
    "-v", f"{mount_ws}:/out_ws",
    task.private["image_name"],
    "sh", "-c", "cp -a . /out_ws/ 2>/dev/null || true"
])
print(f"Extraction code: {code}, files count: {len(list(workspace.iterdir()))}", flush=True)
shutil.copytree(workspace, baseline)

# 2. Test initial evaluation on unpatched codebase
print("\nRunning initial private grading in Docker container...", flush=True)
initial_patch = make_patch(baseline, workspace)
res = evaluate_task_in_container(
    image_name=task.private["image_name"],
    patch=initial_patch,
    test_patch=task.private["test_patch"] if "test_patch" in task.private else None,
    test_cmd=task.private["test_cmd"],
    fail_to_pass=task.private.get("FAIL_TO_PASS", []),
    pass_to_pass=task.private.get("PASS_TO_PASS", []),
    timeout_seconds=60,
)
print(f"Initial grade: resolved={res['resolved']}, fail_to_pass_unresolved={len(res['fail_to_pass_unresolved'])}", flush=True)

# Clean up
remove_dir(test_dir)
print("\nTest completed successfully!", flush=True)
