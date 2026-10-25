import re
from pathlib import Path

target = Path("src/veritas/feedback_runner.py")
code = target.read_text(encoding="utf-8")

# 1. Add safe_rmtree and container imports
helpers = '''import stat
from scripts.veritas_cloud_worker import evaluate_task_in_container, run_cmd, to_container_mount_path

def safe_rmtree(p: Path | str):
    p = Path(p)
    if not p.exists():
        return
    def on_exc(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass
    shutil.rmtree(p, onerror=on_exc)
'''

if "def safe_rmtree" not in code:
    code = code.replace("from .store import EventStore\n", "from .store import EventStore\n" + helpers + "\n")

# 2. Update get_task_setup_fn to support SWE-rebench tasks
setup_logic = '''def get_task_setup_fn(task: Task | str) -> Callable[[Path], tuple[str, str]]:
    """Resolve task setup function from task across SWE-rebench-V2 and fixtures."""
    if isinstance(task, Task) and task.source == "swe_rebench" and task.private.get("image_name"):
        image_name = task.private["image_name"]
        def setup_container_task(ws: Path) -> tuple[str, str]:
            ws.mkdir(parents=True, exist_ok=True)
            mount_ws = to_container_mount_path(ws)
            run_cmd([
                "docker", "run", "--rm",
                "-v", f"{mount_ws}:/out_ws",
                image_name,
                "sh", "-c", "cp -a . /out_ws/ 2>/dev/null || true"
            ])
            return task.repo or "repo", task.prompt
        return setup_container_task

    task_id = task.task_id if isinstance(task, Task) else str(task)
    clean_id = task_id.replace("swe:", "")
    from scripts.run_action_time_tse_experiment import TASK_REGISTRY
    if clean_id in TASK_REGISTRY:
        return TASK_REGISTRY[clean_id]
    for candidate in [clean_id, f"swe_{clean_id}", f"repo_{clean_id}"]:
        if candidate in TASK_REGISTRY:
            return TASK_REGISTRY[candidate]
    raise ValueError(f"No setup function registered for task: {task_id}")
'''

code = re.sub(
    r'def get_task_setup_fn\(task_id: str\) -> Callable\[\[Path\], tuple\[str, str\]\]:.*?(?=\ndef evaluate_workspace)',
    setup_logic,
    code,
    flags=re.DOTALL
)

# 3. Add evaluate_task function
eval_task_func = '''def evaluate_task(task: Task, ws: Path, baseline: Path) -> tuple[bool, str]:
    """Independent grading: evaluate via Docker container for SWE-rebench-V2 or pytest locally."""
    if task.source == "swe_rebench" and task.private.get("image_name"):
        patch = make_patch(baseline, ws)
        res = evaluate_task_in_container(
            image_name=task.private["image_name"],
            patch=patch,
            test_patch=task.private.get("test_patch"),
            test_cmd=task.private.get("test_cmd", "pytest"),
            fail_to_pass=task.private.get("FAIL_TO_PASS", []),
            pass_to_pass=task.private.get("PASS_TO_PASS", []),
            timeout_seconds=90,
        )
        return res.get("resolved", False), res.get("log", "")
    return evaluate_workspace(ws)
'''

if "def evaluate_task" not in code:
    code = code.replace("def evaluate_workspace(ws: Path)", eval_task_func + "\ndef evaluate_workspace(ws: Path)")

# 4. Replace setup_fn = get_task_setup_fn(task_id) with task
code = code.replace("setup_fn = get_task_setup_fn(task_id)", "setup_fn = get_task_setup_fn(task)")

# 5. Replace parent grading and final grading with evaluate_task
code = code.replace(
    "parent_resolved, parent_grade_out = evaluate_workspace(parent_workspace)",
    "parent_resolved, parent_grade_out = evaluate_task(task, parent_workspace, parent_baseline)"
)
code = code.replace(
    "final_resolved, final_grade_out = evaluate_workspace(branch_workspace)",
    "final_resolved, final_grade_out = evaluate_task(task, branch_workspace, branch_baseline)"
)

# 6. Replace shutil.rmtree with safe_rmtree
code = code.replace("shutil.rmtree(parent_workspace)", "safe_rmtree(parent_workspace)")
code = code.replace("shutil.rmtree(parent_baseline)", "safe_rmtree(parent_baseline)")
code = code.replace("shutil.rmtree(branch_dir)", "safe_rmtree(branch_dir)")

target.write_text(code, encoding="utf-8")
print("Successfully patched src/veritas/feedback_runner.py!")
