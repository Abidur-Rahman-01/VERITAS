#!/usr/bin/env python3
"""Autonomous Overnight Novelty Discovery Harness for VERITAS.

Systematically investigates evaluation awareness (D x A) across:
1. Prompt scaffolding: compact vs. explicit software engineering prompt
2. Model architectures: qwen2.5-coder:14b, qwen2.5:14b, llama3.1:8b, gemma3:12b
3. Task difficulty: python-cmd2, sympy, pennylane
4. Downstream policy: Stage 6 static admission gate calibration transfer

Logs all causal contrasts, resolution rates, diff mechanisms, and gate transfer metrics.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERITAS_BIN = Path("/home/user/.venvs/veritas-rebench/bin/veritas")
PYTHON_BIN = Path("/home/user/.venvs/veritas-rebench/bin/python")
SUMMARY_MD = REPO_ROOT / "artifacts" / "overnight_summary.md"


def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted, flush=True)
    with open(REPO_ROOT / "artifacts" / "overnight_execution.log", "a", encoding="utf-8") as f:
        f.write(formatted + "\n")


def run_cmd(args, check=True):
    log(f"EXEC: {' '.join(str(a) for a in args)}")
    result = subprocess.run(args, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if result.stdout:
        log(f"STDOUT: {result.stdout.strip()[:500]}")
    if result.stderr:
        log(f"STDERR: {result.stderr.strip()[:500]}")
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed (exit {result.returncode}): {result.stderr}")
    return result


def append_summary(section_title, markdown_content):
    with open(SUMMARY_MD, "a", encoding="utf-8") as f:
        f.write(f"\n\n## {section_title}\n\n{markdown_content}\n")


def post_process_study(study_path):
    """Run full evaluation pipeline: grade -> audit -> measure -> check-cue -> verify -> report."""
    study = str(study_path)
    log(f"Post-processing study: {study}")

    # 1. Grade
    run_cmd([str(VERITAS_BIN), "awareness", "grade", "--study", study], check=False)
    # 2. Audit
    run_cmd([str(VERITAS_BIN), "awareness", "audit", "--study", study], check=False)
    # 3. Measure
    run_cmd([str(VERITAS_BIN), "awareness", "measure", "--study", study], check=False)
    # 4. Check Cue
    run_cmd([str(VERITAS_BIN), "awareness", "check-cue", "--study", study], check=False)
    # 5. Verify integrity
    run_cmd([str(VERITAS_BIN), "awareness", "verify", "--study", study], check=False)
    # 6. Report
    run_cmd([str(VERITAS_BIN), "awareness", "report", "--study", study], check=False)

    report_json_path = Path(study) / "report" / "report.json"
    report_md_path = Path(study) / "report" / "report.md"
    outcomes_csv_path = Path(study) / "report" / "outcomes.csv"

    results = {"study": study, "resolved": 0, "total": 0, "contrasts": {}}
    if report_json_path.exists():
        data = json.loads(report_json_path.read_text(encoding="utf-8"))
        results["data"] = data
        results["resolved"] = data.get("resolved_count", 0)
        results["total"] = data.get("total_trials", 0)
        results["contrasts"] = data.get("contrasts", {})

    if report_md_path.exists():
        results["summary_table"] = report_md_path.read_text(encoding="utf-8")

    return results


def wait_for_current_run(study_path, max_wait_seconds=1800):
    """Wait for study.sqlite to finish all scheduled trials."""
    log(f"Waiting for active run in {study_path}...")
    start = time.time()
    plan_file = Path(study_path) / "plan.json"
    if not plan_file.exists():
        log("No plan.json found; skipping wait.")
        return

    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    expected_trials = plan.get("trials", 4)

    while time.time() - start < max_wait_seconds:
        # Check outcomes in trial directories
        trials_dir = Path(study_path) / "trials"
        if trials_dir.exists():
            outcomes = list(trials_dir.glob("*/attempt-*/outcome.json"))
            if len(outcomes) >= expected_trials:
                log(f"All {expected_trials} trials have completed.")
                time.sleep(2)
                return
        time.sleep(10)
    log("Wait timeout reached; proceeding to post-processing.")


def run_full_study(config_path, study_path):
    """Clean, plan, execute, and evaluate a complete study."""
    cfg = str(config_path)
    study = str(study_path)
    log(f"--- STARTING FULL STUDY: {cfg} -> {study} ---")

    if Path(study).exists():
        shutil.rmtree(study)

    # 1. Plan
    run_cmd([str(VERITAS_BIN), "awareness", "plan", "--config", cfg, "--output", study])

    # 2. Run
    run_cmd([str(VERITAS_BIN), "awareness", "run", "--study", study], check=False)

    # 3. Post-process
    results = post_process_study(study)
    return results


def main():
    log("=== OVERNIGHT NOVELTY DISCOVERY HARNESS LAUNCHED ===")
    if not SUMMARY_MD.exists():
        SUMMARY_MD.write_text("# VERITAS Overnight Autonomous Novelty Discovery Report\n\n", encoding="utf-8")

    # PHASE 1: Wait for and evaluate the currently running trial (Trial Qwen14b Compact)
    log("PHASE 1: Finalizing currently active trial_qwen14b...")
    active_study = REPO_ROOT / "artifacts" / "trial_qwen14b"
    wait_for_current_run(active_study)
    res1 = post_process_study(active_study)
    append_summary("Phase 1: Initial Trial (qwen2.5-coder:14b, compact prompt)",
                   f"Completed {res1.get('total', 4)} trials on `cmd2-744`.\n\n"
                   f"```\n{res1.get('summary_table', 'No report table generated')}\n```")

    # PHASE 2: Test Explicit SE Scaffolding (compact: false)
    # Hypothesized breakthrough: explicit edit_file/read_file instructions prevent the model
    # from getting stuck in python REPL simulation and force concrete repository file edits!
    log("PHASE 2: Testing Explicit SE Scaffolding (compact: false)...")
    cfg_verbose = REPO_ROOT / "configs" / "awareness-trial-qwen14b-verbose.yaml"
    study_verbose = REPO_ROOT / "artifacts" / "trial_qwen14b_verbose"
    
    # Read base config and update compact: false
    base_cfg = json.loads(json.dumps(
        __import__("yaml").safe_load((REPO_ROOT / "configs" / "awareness-trial-qwen14b.yaml").read_text(encoding="utf-8"))
    ))
    base_cfg["compact"] = False
    base_cfg["name"] = "trial-qwen14b-verbose"
    with open(cfg_verbose, "w", encoding="utf-8") as f:
        __import__("yaml").dump(base_cfg, f)

    res2 = run_full_study(cfg_verbose, study_verbose)
    append_summary("Phase 2: Scaffolding Comparison (qwen2.5-coder:14b, explicit prompt)",
                   f"Tested explicit SE prompt vs compact prompt.\n\n"
                   f"```\n{res2.get('summary_table', 'No report table generated')}\n```")

    # PHASE 3: Multi-Model Architecture Check (qwen2.5:14b general vs. llama3.1:8b)
    log("PHASE 3: Comparing Model Architectures...")
    models_to_test = [
        {"id": "actor-llama", "family": "llama", "name": "llama3.1:8b",
         "rev": "46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e"},
        {"id": "actor-qwen-general", "family": "qwen", "name": "qwen2.5:14b",
         "rev": "7cdf5a0187d5c58cc5d369b255592f7841d1c4696d45a8c8a9489440385b22f6"}
    ]

    for m in models_to_test:
        log(f"Testing model architecture: {m['name']}...")
        cfg_m = REPO_ROOT / "configs" / f"awareness-trial-{m['id']}.yaml"
        study_m = REPO_ROOT / "artifacts" / f"trial_{m['id']}"
        m_cfg = json.loads(json.dumps(base_cfg))
        m_cfg["name"] = f"trial-{m['id']}"
        m_cfg["actors"] = [{
            "id": m["id"],
            "family": m["family"],
            "revision": m["rev"],
            "model": {
                "backend": "ollama",
                "base_url": "http://172.23.16.1:11434",
                "name": m["name"],
                "max_tokens": 2048,
                "temperature": 0
            }
        }]
        with open(cfg_m, "w", encoding="utf-8") as f:
            __import__("yaml").dump(m_cfg, f)

        res_m = run_full_study(cfg_m, study_m)
        append_summary(f"Phase 3: Model Architecture ({m['name']})",
                       f"```\n{res_m.get('summary_table', 'No report table generated')}\n```")

    # PHASE 4: Deep Dive & Multi-Task Expansion
    log("PHASE 4: Deep Dive & Multi-Task Cohort Expansion...")
    # Expand to 4 tasks across cmd2, sympy-19512, sympy-20967, pennylane-5063
    cfg_deep = REPO_ROOT / "configs" / "awareness-trial-deepdive.yaml"
    study_deep = REPO_ROOT / "artifacts" / "study_deepdive"
    deep_cfg = json.loads(json.dumps(base_cfg))
    deep_cfg["name"] = "veritas-overnight-deepdive"
    deep_cfg["task_ids"] = None
    deep_cfg["task_limit"] = 4
    with open(cfg_deep, "w", encoding="utf-8") as f:
        __import__("yaml").dump(deep_cfg, f)

    res_deep = run_full_study(cfg_deep, study_deep)
    append_summary("Phase 4: Multi-Task Deep Dive Cohort (4 Tasks across Repositories)",
                   f"```\n{res_deep.get('summary_table', 'No report table generated')}\n```")

    # PHASE 5: Stage 6 Admission Gate Calibration & Policy Transfer
    log("PHASE 5: Stage 6 Static Gate Calibration & Policy Transfer...")
    gate_score_file = REPO_ROOT / "artifacts" / "gate_score.json"
    try:
        run_cmd([str(VERITAS_BIN), "awareness", "fit-gate",
                 "--study", str(study_deep),
                 "--output", str(gate_score_file)])
        append_summary("Phase 5: Gate Calibration Fit",
                       f"Successfully fitted patch risk scorer: `{gate_score_file}`.")
    except Exception as e:
        log(f"Gate fit skipped or failed: {e}")

    log("=== OVERNIGHT NOVELTY DISCOVERY HARNESS COMPLETED ALL PHASES ===")


if __name__ == "__main__":
    main()
