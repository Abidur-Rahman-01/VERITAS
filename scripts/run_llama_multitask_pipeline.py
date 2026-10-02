import os
import subprocess
import sys
import time
from datetime import datetime

LOG_FILE = "artifacts/llama_multitask_execution.log"
STUDY_DIR = "/mnt/d/2110001/VERITAS/artifacts/study_llama_multitask"
VENV_BIN = "/home/user/.venvs/veritas-rebench/bin"

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(formatted + "\n")

def run_wsl(cmd_str):
    full_cmd = f'wsl -d Ubuntu bash -c "cd /mnt/d/2110001/VERITAS && {cmd_str}"'
    log(f"EXEC: {cmd_str}")
    start = time.time()
    p = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    duration = time.time() - start
    if p.stdout.strip():
        preview = p.stdout.strip()[:300].replace('\n', ' ')
        log(f"STDOUT: {preview}")
    if p.stderr.strip():
        preview = p.stderr.strip()[:300].replace('\n', ' ')
        log(f"STDERR: {preview}")
    if p.returncode != 0:
        log(f"ERROR: Exit code {p.returncode} after {duration:.1f}s")
        return False
    log(f"SUCCESS in {duration:.1f}s")
    return True

def main():
    log("=== LLAMA 3.1 MULTI-TASK FACTORIAL CONFIRMATION RUN LAUNCHED ===")
    
    # 1. Run the actor trial sessions
    log(f"Step 1: Running study execution: {STUDY_DIR}")
    if not run_wsl(f"{VENV_BIN}/veritas awareness run --study {STUDY_DIR}"):
        log("Execution encountered an error. Stopping.")
        sys.exit(1)
        
    # 2. Grade
    log("Step 2: Grading generated patches with SWE-bench...")
    run_wsl(f"{VENV_BIN}/veritas awareness grade --study {STUDY_DIR}")
    
    # 3. Audit
    log("Step 3: Auditing reviewer assignments and blinded traces...")
    run_wsl(f"{VENV_BIN}/veritas awareness audit --study {STUDY_DIR}")
    
    # 4. Measure
    log("Step 4: Measuring defensive metrics and language stats...")
    run_wsl(f"{VENV_BIN}/veritas awareness measure --study {STUDY_DIR}")
    
    # 5. Check-cue
    log("Step 5: Running post-hoc cue comprehension checks...")
    run_wsl(f"{VENV_BIN}/veritas awareness check-cue --study {STUDY_DIR}")
    
    # 6. Verify
    log("Step 6: Verifying cryptographic protocol integrity...")
    run_wsl(f"{VENV_BIN}/veritas awareness verify --study {STUDY_DIR}")
    
    # 7. Report
    log("Step 7: Compiling statistical contrast report...")
    run_wsl(f"{VENV_BIN}/veritas awareness report --study {STUDY_DIR}")
    
    # 8. Update trajectory and intermediate utility analysis
    log("Step 8: Re-running cross-study intermediate utility and trajectory analysis...")
    subprocess.run("python scripts/analyze_intermediate_utility.py", shell=True)
    
    log("=== LLAMA 3.1 MULTI-TASK CONFIRMATION COMPLETED ALL STEPS ===")

if __name__ == "__main__":
    main()
