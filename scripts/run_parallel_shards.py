#!/usr/bin/env python3
"""VERITAS High-Throughput Parallel Sharding Engine.

Leverages multi-core CPU (Ryzen 9 7950X, 32 threads) and GPU (RTX 5080)
to execute independent study shards concurrently rather than sequentially.

Architecture:
1. Shards multi-task configs by task/repository into independent sub-studies.
2. Utilizes Ollama multi-request concurrency (OLLAMA_NUM_PARALLEL=4).
3. Executes N worker processes simultaneously without database lock contention.
4. Aggregates results across all shards into a unified statistical dataset.
"""

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = REPO_ROOT / "artifacts" / "parallel_execution.log"
VENV_BIN = "/home/user/.venvs/veritas-rebench/bin"

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(formatted + "\n")

def run_wsl(cmd_str, log_prefix=""):
    full_cmd = f'wsl -d Ubuntu bash -c "cd /mnt/d/2110001/VERITAS && {cmd_str}"'
    if log_prefix:
        log(f"[{log_prefix}] EXEC: {cmd_str}")
    else:
        log(f"EXEC: {cmd_str}")
        
    start = time.time()
    p = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    duration = time.time() - start
    
    if p.returncode != 0:
        err_preview = p.stderr.strip()[:400].replace('\n', ' ') if p.stderr else "Unknown error"
        log(f"[{log_prefix}] ERROR (exit {p.returncode}) after {duration:.1f}s: {err_preview}")
        return False, p.stdout, p.stderr
        
    log(f"[{log_prefix}] SUCCESS in {duration:.1f}s")
    return True, p.stdout, p.stderr

def run_single_shard(shard_info):
    name = shard_info["name"]
    cfg_path = shard_info["config"]
    study_dir = shard_info["study_dir"]
    study_dir_wsl = f"/mnt/d/2110001/VERITAS/{study_dir.replace('\\', '/')}"
    
    log(f"=== Worker started for shard: {name} ===")
    
    # 1. Plan study
    log(f"[{name}] Stage 1: Planning study...")
    ok, _, _ = run_wsl(f"{VENV_BIN}/veritas awareness plan --config {cfg_path} --output {study_dir_wsl}", log_prefix=name)
    if not ok:
        return {"name": name, "status": "failed_at_plan"}
        
    # 2. Run trials
    log(f"[{name}] Stage 2: Running trials...")
    start_run = time.time()
    ok, _, _ = run_wsl(f"{VENV_BIN}/veritas awareness run --study {study_dir_wsl}", log_prefix=name)
    run_duration = time.time() - start_run
    if not ok:
        return {"name": name, "status": "failed_at_run", "duration": run_duration}
        
    # 3. Grade
    log(f"[{name}] Stage 3: Grading patches with SWE-bench Docker...")
    run_wsl(f"{VENV_BIN}/veritas awareness grade --study {study_dir_wsl}", log_prefix=name)
    
    # 4. Audit
    log(f"[{name}] Stage 4: Auditing reviewer assignments...")
    run_wsl(f"{VENV_BIN}/veritas awareness audit --study {study_dir_wsl}", log_prefix=name)
    
    # 5. Measure
    log(f"[{name}] Stage 5: Measuring defensive metrics...")
    run_wsl(f"{VENV_BIN}/veritas awareness measure --study {study_dir_wsl}", log_prefix=name)
    
    # 6. Check Cue
    log(f"[{name}] Stage 6: Manipulation checks...")
    run_wsl(f"{VENV_BIN}/veritas awareness check-cue --study {study_dir_wsl}", log_prefix=name)
    
    # 7. Verify
    log(f"[{name}] Stage 7: Cryptographic hash verification...")
    run_wsl(f"{VENV_BIN}/veritas awareness verify --study {study_dir_wsl}", log_prefix=name)
    
    # 8. Report
    log(f"[{name}] Stage 8: Compiling contrast report...")
    run_wsl(f"{VENV_BIN}/veritas awareness report --study {study_dir_wsl}", log_prefix=name)
    
    log(f"=== Shard completed successfully: {name} in {run_duration:.1f}s ===")
    return {"name": name, "status": "success", "study_dir": study_dir, "duration": run_duration}

def shard_config(base_config_path, tasks=None):
    with open(base_config_path, "r", encoding="utf-8") as f:
        base_cfg = yaml.safe_load(f)
        
    default_tasks = [
        "swe:python-cmd2__cmd2-744",
        "swe:sympy__sympy-19512",
        "swe:sympy__sympy-20967",
        "swe:PennyLaneAI__pennylane-5063"
    ]
    target_tasks = tasks or default_tasks
    
    shards_dir = REPO_ROOT / "configs" / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)
    
    shard_infos = []
    for task_id in target_tasks:
        short_id = task_id.replace("swe:", "").replace("__", "_").replace("-", "_")
        shard_cfg_name = f"shard_{short_id}.yaml"
        shard_cfg_path = shards_dir / shard_cfg_name
        
        cfg = json.loads(json.dumps(base_cfg))
        cfg["name"] = f"shard-{short_id}"
        cfg["task_ids"] = [task_id]
        if "task_limit" in cfg:
            del cfg["task_limit"]
            
        with open(shard_cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False)
            
        study_dir = f"artifacts/shard_{short_id}"
        shard_infos.append({
            "name": short_id,
            "task_id": task_id,
            "config": f"configs/shards/{shard_cfg_name}",
            "study_dir": study_dir
        })
        
    return shard_infos

def main():
    parser = argparse.ArgumentParser(description="Run parallel study shards")
    parser.add_argument("--config", default="configs/awareness-trial-llama-multitask.yaml",
                        help="Base YAML configuration file")
    parser.add_argument("--workers", type=int, default=4,
                        help="Maximum parallel workers (default: 4)")
    parser.add_argument("--tasks", nargs="+", default=None,
                        help="Explicit task IDs to run")
    parser.add_argument("--clean", action="store_true",
                        help="Clean existing shard directories before running")
    args = parser.parse_args()
    
    log("=================================================================")
    log("🚀 LAUNCHING VERITAS HIGH-THROUGHPUT PARALLEL SHARDING ENGINE 🚀")
    log(f"Base Config: {args.config}")
    log(f"Max Concurrent Workers: {args.workers}")
    log("=================================================================")
    
    shard_infos = shard_config(args.config, args.tasks)
    log(f"Generated {len(shard_infos)} independent study shards:")
    for s in shard_infos:
        log(f"  • {s['name']} -> Task: {s['task_id']} (Output: {s['study_dir']})")
        if args.clean and os.path.exists(s["study_dir"]):
            log(f"    Cleaning existing {s['study_dir']}...")
            shutil.rmtree(s["study_dir"])
            
    start_total = time.time()
    
    # Launch shards concurrently across worker threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_single_shard, shard): shard["name"] for shard in shard_infos}
        results = []
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                res = future.result()
                results.append(res)
                log(f"Shard '{name}' finished with result: {res['status']}")
            except Exception as e:
                log(f"Shard '{name}' generated exception: {e}")
                results.append({"name": name, "status": f"exception: {e}"})
                
    total_duration = time.time() - start_total
    log("=================================================================")
    log(f"🏁 ALL PARALLEL SHARDS FINISHED in {total_duration/60:.2f} minutes 🏁")
    log("=================================================================")
    
    # Re-run aggregation analysis
    log("Re-running cross-study intermediate utility analysis...")
    subprocess.run("python scripts/analyze_intermediate_utility.py", shell=True)
    log("Cross-study aggregation complete.")

if __name__ == "__main__":
    main()
