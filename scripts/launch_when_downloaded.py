#!/usr/bin/env python3
"""
Orchestrator: Waits for Ollama to finish pulling codestral (22B Coder),
then resets the study for a pure 20B+ run and launches the benchmark.
"""

import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

MODEL = "codestral"
STUDY_DIR = Path("runs/feedback_study_v2_500")


def check_model_ready():
    try:
        res = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        return MODEL in res.stdout
    except Exception:
        return False


def main():
    print(f"Waiting for {MODEL} to finish downloading from Ollama...", flush=True)
    start = time.time()
    while not check_model_ready():
        time.sleep(10)
        elapsed = int(time.time() - start)
        if elapsed % 30 == 0:
            print(f"  Still downloading {MODEL} ({elapsed // 60}m {elapsed % 60}s elapsed)...", flush=True)

    print(f"\n=======================================================", flush=True)
    print(f"SUCCESS: {MODEL} (22B Coder) is downloaded and ready in Ollama!", flush=True)
    print(f"Resetting study records for clean restart from Block 1...", flush=True)
    print(f"=======================================================\n", flush=True)

    # 1. Clean previous results
    res_file = STUDY_DIR / "results.jsonl"
    if res_file.exists():
        res_file.write_text("", encoding="utf-8")
        print("  - Cleared results.jsonl", flush=True)

    # 2. Clean previous block folders
    blocks_dir = STUDY_DIR / "blocks"
    if blocks_dir.exists():
        def on_exc(func, p, exc_info):
            try:
                os.chmod(p, stat.S_IWRITE)
                func(p)
            except Exception:
                pass
        for b in blocks_dir.iterdir():
            if b.is_dir():
                shutil.rmtree(b, onerror=on_exc)
        print("  - Cleared blocks directory", flush=True)

    print("Launching benchmark study from the beginning (Block 1) with Codestral 22B...", flush=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    env["PYTHONUNBUFFERED"] = "1"

    cmd = [
        sys.executable, "-u", "-m", "veritas", "feedback-study", "run",
        "--study", str(STUDY_DIR),
        "--actor", MODEL,
        "--draft-steps", "6",
        "--revision-steps", "8",
        "--budget", "40.0",
        "--no-resume"
    ]

    log_path = STUDY_DIR / "codestral_run.log"
    with open(log_path, "w", encoding="utf-8") as out:
        proc = subprocess.Popen(cmd, env=env, stdout=out, stderr=subprocess.STDOUT)
        print(f"Benchmark started with PID {proc.pid}. Logging to {log_path}", flush=True)
        proc.wait()


if __name__ == "__main__":
    main()
