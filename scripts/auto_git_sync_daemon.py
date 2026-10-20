"""
auto_git_sync_daemon.py

Continuous Git Synchronization Daemon for VERITAS 5-Model 900-Trial Benchmark.
Periodically checks for completed trials and commits & pushes results to GitHub.
Upon completion of the runner process, performs a final master synthesis, commit, and push.
"""

import os
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_cmd(cmd_list):
    try:
        res = subprocess.run(
            cmd_list,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        return res.returncode, res.stdout, res.stderr
    except Exception as e:
        return -1, "", str(e)


def has_git_changes():
    code, stdout, _ = run_cmd(["git", "status", "--porcelain"])
    if code != 0:
        return False
    # Check if there are changes in artifacts, docs, or PAPER
    lines = stdout.strip().splitlines()
    relevant = [
        l for l in lines
        if any(k in l for k in ["artifacts/", "docs/", "PAPER", "scripts/"])
    ]
    return len(relevant) > 0


def commit_and_push(commit_msg: str):
    print(f"[{time.strftime('%X')}] Committing and pushing: {commit_msg}")
    run_cmd(["git", "add", "artifacts/", "docs/", "PAPER.md", "PAPER_TSE.md", "scripts/"])
    code, out, err = run_cmd(["git", "commit", "-m", commit_msg])
    if code == 0:
        print(f"[{time.strftime('%X')}] Commit successful: {out.strip().splitlines()[0] if out else ''}")
        p_code, p_out, p_err = run_cmd(["git", "push", "origin", "main"])
        if p_code == 0:
            print(f"[{time.strftime('%X')}] PUSH TO GITHUB SUCCESSFUL.")
        else:
            print(f"[{time.strftime('%X')}] Push failed: {p_err}")
    else:
        print(f"[{time.strftime('%X')}] Nothing to commit or commit failed.")


def is_runner_active():
    try:
        # Check if python process running run_5_coder_models_180_trials is alive
        res = subprocess.run(
            ["powershell", "-Command", "Get-Process python -ErrorAction SilentlyContinue | Select-Object Id, ProcessName"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return "python" in res.stdout.lower()
    except Exception:
        return True


def check_models_completion():
    models = [
        "qwen2.5_coder_14b",
        "deepseek_coder_v2_16b",
        "granite_code_20b",
        "starcoder2_15b",
        "qwen2.5_coder_30b",
    ]
    completed = []
    for m in models:
        rep = REPO_ROOT / "artifacts" / f"action_time_study_{m}" / "action_time_report.json"
        if rep.exists():
            completed.append(m)
    return completed


def main():
    print(f"[{time.strftime('%X')}] Starting Auto-Git Synchronization Daemon for 5-Model Benchmark...")
    sync_interval_sec = 180  # Check every 3 minutes
    last_completed_models = set()

    consecutive_inactive = 0

    while True:
        time.sleep(sync_interval_sec)

        completed_models = set(check_models_completion())
        new_completed = completed_models - last_completed_models
        for m in new_completed:
            commit_and_push(f"Complete 180 trials for model {m} and update reports")
            last_completed_models.add(m)

        if has_git_changes():
            commit_and_push("Checkpoint: update progressive benchmark trials and reports")

        active = is_runner_active()
        if not active:
            consecutive_inactive += 1
            if consecutive_inactive >= 2:
                print(f"[{time.strftime('%X')}] Benchmark runner has terminated.")
                # Final push
                if has_git_changes():
                    commit_and_push("Final: Complete 5-model 900-trial Action-Time Verification benchmark suite")
                print(f"[{time.strftime('%X')}] Auto-sync daemon completed.")
                break
        else:
            consecutive_inactive = 0


if __name__ == "__main__":
    main()
