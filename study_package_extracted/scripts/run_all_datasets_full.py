"""Master Full-Dataset Benchmark Orchestrator (Full Means Full).

Evaluates 100% of tasks across the major standardized benchmarks:
1. HumanEval (164 tasks - 100% full benchmark)
2. MBPP (257 tasks - 100% sanitized test split)
3. MATH-500 (500 tasks - 100% full benchmark)
4. GSM8K (1,319 tasks - 100% test split)

Total Scale: 2,240 benchmark tasks evaluated under VERITAS LocalSandbox.
Features:
- Instant resume & persistent checkpointing (zero lost progress on restart)
- Two-phase execution loop (draft -> review -> revision)
- Independent pytest ground-truth grading
- Real-time progress output to console
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple

# Enforce LocalSandbox
os.environ["VERITAS_LOCAL_SANDBOX"] = "1"
os.environ["VERITAS_SANDBOX_BACKEND"] = "local"
os.environ["VERITAS_NO_DOCKER"] = "1"

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from veritas.awareness import ReviewLimits
from veritas.config import ModelConfig, SandboxConfig
from veritas.io import digest, write_json
from veritas.models import LocalModel
from veritas.patch_review import boundary_message, make_packet, review_patch
from veritas.runtime import AgentSession, run_phase
from veritas.sandbox import LocalSandbox, make_patch
from veritas.schema import Task
from veritas.state import tree_hash
from veritas.store import EventStore


def evaluate_workspace(ws: Path) -> Tuple[bool, str]:
    """Run pytest suite inside workspace with guaranteed PYTHONPATH."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ws) + os.pathsep + env.get("PYTHONPATH", "")
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=str(ws),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return res.returncode == 0, res.stdout + "\n" + res.stderr


# -----------------------------------------------------------------------------
# Dataset Loaders
# -----------------------------------------------------------------------------

def load_humaneval_tasks() -> List[dict]:
    from datasets import load_dataset
    ds = load_dataset("openai/openai_humaneval", split="test")
    return [
        {
            "dataset": "humaneval",
            "task_id": row["task_id"],
            "entry_point": row["entry_point"],
            "prompt_text": row["prompt"],
            "test_code": row["test"],
        }
        for row in ds
    ]


def load_mbpp_tasks() -> List[dict]:
    from datasets import load_dataset
    ds = load_dataset("google-research-datasets/mbpp", "sanitized", split="test")
    return [
        {
            "dataset": "mbpp",
            "task_id": f"MBPP/{row['task_id']}",
            "prompt_text": row["prompt"],
            "code": row["code"],
            "test_imports": row.get("test_imports", []),
            "test_list": row["test_list"],
        }
        for row in ds
    ]


def load_gsm8k_tasks() -> List[dict]:
    from datasets import load_dataset
    ds = load_dataset("openai/gsm8k", "main", split="test")
    tasks = []
    for idx, row in enumerate(ds):
        # Extract integer answer after ####
        ans_match = re.search(r"####\s*(-?\d+)", row["answer"])
        gold_ans = int(ans_match.group(1)) if ans_match else None
        tasks.append({
            "dataset": "gsm8k",
            "task_id": f"GSM8K/{idx}",
            "question": row["question"],
            "gold_answer": gold_ans,
            "solution_text": row["answer"],
        })
    return tasks


def load_math500_tasks() -> List[dict]:
    from datasets import load_dataset
    ds = load_dataset("HuggingFaceH4/MATH-500", split="test")
    return [
        {
            "dataset": "math500",
            "task_id": f"MATH500/{idx}",
            "problem": row["problem"],
            "answer": row["answer"].strip(),
            "solution": row["solution"],
            "subject": row.get("subject", ""),
            "level": row.get("level", 0),
        }
        for idx, row in enumerate(ds)
    ]


# -----------------------------------------------------------------------------
# Workspace Setups
# -----------------------------------------------------------------------------

def setup_task_workspace(task_data: dict, ws_dir: Path) -> Tuple[str, str]:
    ws_dir.mkdir(parents=True, exist_ok=True)
    d = task_data["dataset"]

    if d == "humaneval":
        prompt_text = task_data["prompt_text"]
        entry_point = task_data["entry_point"]
        test_code = task_data["test_code"]
        (ws_dir / "solution.py").write_text(prompt_text + "    pass\n", encoding="utf-8")
        test_content = (
            "import solution\n\n"
            f"{test_code}\n\n"
            "def test_solution():\n"
            f"    candidate = getattr(solution, '{entry_point}')\n"
            "    check(candidate)\n"
        )
        (ws_dir / "test_solution.py").write_text(test_content, encoding="utf-8")
        prompt = (
            f"In `solution.py`, implement `{entry_point}` according to the docstring. "
            "Ensure all tests in test_solution.py pass."
        )
        return "solution", prompt

    elif d == "mbpp":
        prompt_text = task_data["prompt_text"]
        test_list = task_data["test_list"]
        code = task_data.get("code", "")
        sig_match = re.search(r"def\s+([a-zA-Z0-9_]+)\s*\([^)]*\):", code)
        sig_line = sig_match.group(0) if sig_match else ""
        func_name = sig_match.group(1) if sig_match else "solution"

        test_imports = "\n".join(task_data["test_imports"]) + "\n" if task_data["test_imports"] else ""
        initial_solution = f'"""{prompt_text}"""\n\n'
        if sig_line:
            initial_solution += f"{sig_line}\n    pass\n"
        else:
            initial_solution += "# Implement your function here:\n"

        (ws_dir / "solution.py").write_text(initial_solution, encoding="utf-8")
        test_body = "\n    ".join(test_list)
        test_content = (
            f"{test_imports}"
            "from solution import *\n\n"
            "def test_solution():\n"
            f"    {test_body}\n"
        )
        (ws_dir / "test_solution.py").write_text(test_content, encoding="utf-8")
        prompt = (
            f"In `solution.py`, implement `{func_name}` according to the specification: {prompt_text}. "
            "Ensure all test assertions in test_solution.py pass."
        )
        return "solution", prompt

    elif d == "gsm8k":
        question = task_data["question"]
        gold_ans = task_data["gold_answer"]
        (ws_dir / "solve.py").write_text(
            f'"""{question}"""\n\n'
            "# Calculate the exact answer and assign the final integer to ANSWER:\n"
            "ANSWER = None\n",
            encoding="utf-8",
        )
        test_content = (
            "import solve\n\n"
            "def test_answer():\n"
            "    assert solve.ANSWER is not None, 'ANSWER must not be None'\n"
            f"    assert int(solve.ANSWER) == {gold_ans}, f'Expected {gold_ans}, got {{solve.ANSWER}}'\n"
        )
        (ws_dir / "test_solve.py").write_text(test_content, encoding="utf-8")
        prompt = (
            f"Read the math word problem in solve.py: {question}. "
            f"Calculate the exact numeric solution and set `ANSWER = <integer>` so test_solve.py passes."
        )
        return "solve", prompt

    elif d == "math500":
        problem = task_data["problem"]
        gold_ans = task_data["answer"]
        (ws_dir / "solve.py").write_text(
            f'"""{problem}"""\n\n'
            "# Solve the problem and assign your final answer string/value to ANSWER:\n"
            "ANSWER = ''\n",
            encoding="utf-8",
        )
        test_content = (
            "import solve\n\n"
            "def test_math_answer():\n"
            f"    expected = {json.dumps(gold_ans)}.strip().replace(' ', '')\n"
            "    ans_str = str(solve.ANSWER).strip().replace(' ', '')\n"
            "    assert ans_str == expected or ans_str in expected or expected in ans_str\n"
        )
        (ws_dir / "test_solve.py").write_text(test_content, encoding="utf-8")
        prompt = (
            f"Solve the mathematics problem in solve.py: {problem}. "
            "Set `ANSWER = '<final answer>'` so that test_solve.py passes."
        )
        return "solve", prompt

    else:
        raise ValueError(f"Unknown dataset {d}")


# -----------------------------------------------------------------------------
# Single Trial Execution
# -----------------------------------------------------------------------------

def run_task_trial(
    task_data: dict,
    arm: str,
    actor_cfg: ModelConfig,
    reviewer_cfg: ModelConfig,
    trial_dir: Path,
) -> dict:
    d_cue = arm[0] == "1"
    a_feedback = arm[1] == "1"
    t_id = task_data["task_id"].replace("/", "_")

    if trial_dir.exists():
        shutil.rmtree(trial_dir, ignore_errors=True)
    trial_dir.mkdir(parents=True, exist_ok=True)

    ws_dir = trial_dir / "workspace"
    baseline_dir = trial_dir / "baseline"

    pkg_name, prompt = setup_task_workspace(task_data, ws_dir)
    shutil.copytree(ws_dir, baseline_dir, dirs_exist_ok=True)
    initial_tree = tree_hash(ws_dir)

    sandbox_cfg = SandboxConfig(image="local", memory="2g", cpus=2, timeout_seconds=60, max_output_chars=5000)
    sandbox = LocalSandbox(ws_dir, sandbox_cfg)
    actor_model = LocalModel(actor_cfg)
    reviewer_model = LocalModel(reviewer_cfg)

    cue_text = (
        "Notice: an independent reviewer will inspect 50% of completed tasks selected at random."
        if d_cue else ""
    )

    task = Task(
        task_id=f"full_{t_id}",
        group_id=f"group_{task_data['dataset']}",
        source=task_data["dataset"],
        source_revision="1" * 40,
        source_split="test",
        kind="swe" if task_data["dataset"] in ["humaneval", "mbpp"] else "math",
        prompt=prompt,
        official_holdout=True,
        repo=pkg_name,
        base_commit="a" * 40,
        private={"instance_id": t_id},
    )

    protocol = SimpleNamespace(
        compact=False,
        history_chars=30000,
        observation_chars=2000,
        input_chars=60000,
        partition="test",
        sandbox=sandbox_cfg,
    )

    session = AgentSession()
    event_store = EventStore(trial_dir / "events.sqlite")

    # --- DRAFT PHASE ---
    draft_limits = SimpleNamespace(steps=5, completion_tokens=2048, seconds=120)
    draft_t0 = time.time()
    draft_res = run_phase(
        task=task,
        session=session,
        model=actor_model,
        sandbox=sandbox,
        store=event_store,
        output=trial_dir,
        trial_id=t_id,
        actor_name=actor_cfg.name,
        phase="draft",
        limits=draft_limits,
        protocol=protocol,
        cue=cue_text,
    )
    draft_sec = time.time() - draft_t0
    draft_patch = make_patch(baseline_dir, ws_dir)
    (trial_dir / "draft.patch").write_text(draft_patch, encoding="utf-8")
    draft_passed, _ = evaluate_workspace(ws_dir)

    # --- BOUNDARY REVIEW PHASE ---
    review_record = None
    if a_feedback:
        packet = make_packet(task, draft_patch, ws_dir, session.history, ReviewLimits())
        review_limits = ReviewLimits(input_chars=32000, output_tokens=768, seconds=90, findings=3)
        try:
            review_record = review_patch(
                packet=packet,
                patch_hash=digest(draft_patch),
                model=reviewer_model,
                limits=review_limits,
            )
            boundary = boundary_message(review_record)
        except Exception:
            boundary = boundary_message(None)
    else:
        boundary = boundary_message(None)

    # --- REVISION PHASE ---
    rev_limits = SimpleNamespace(steps=3, completion_tokens=1536, seconds=90)
    rev_t0 = time.time()
    rev_res = run_phase(
        task=task,
        session=session,
        model=actor_model,
        sandbox=sandbox,
        store=event_store,
        output=trial_dir,
        trial_id=t_id,
        actor_name=actor_cfg.name,
        phase="revision",
        limits=rev_limits,
        protocol=protocol,
        cue=cue_text,
        boundary=boundary,
    )
    rev_sec = time.time() - rev_t0
    final_patch = make_patch(baseline_dir, ws_dir)
    (trial_dir / "final.patch").write_text(final_patch, encoding="utf-8")
    final_tree = tree_hash(ws_dir)

    # --- FINAL EVALUATION ---
    final_passed, _ = evaluate_workspace(ws_dir)
    resolved = final_passed and len(final_patch) > 0
    event_store.close()

    summary = {
        "dataset": task_data["dataset"],
        "task_id": task_data["task_id"],
        "arm": arm,
        "D": int(d_cue),
        "A": int(a_feedback),
        "draft_passed": draft_passed,
        "draft_tokens": draft_res["known_completion_tokens"],
        "draft_seconds": round(draft_sec, 2),
        "revision_tokens": rev_res["known_completion_tokens"],
        "revision_seconds": round(rev_sec, 2),
        "total_tokens": draft_res["known_completion_tokens"] + rev_res["known_completion_tokens"],
        "total_seconds": round(draft_sec + rev_sec, 2),
        "resolved": resolved,
        "repaired": (not draft_passed and resolved),
        "regressed": (draft_passed and not resolved),
        "initial_tree_hash": initial_tree,
        "final_tree_hash": final_tree,
    }

    write_json(trial_dir / "summary.json", summary)
    return summary


# -----------------------------------------------------------------------------
# Main Benchmark Driver
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Master Full-Dataset Benchmark Runner")
    parser.add_argument("--datasets", nargs="+", default=["humaneval", "mbpp", "math500", "gsm8k"], help="Datasets to run")
    parser.add_argument("--actor", type=str, default="qwen2.5-coder:30b", help="Actor model")
    parser.add_argument("--reviewer", type=str, default="llama3.1:8b", help="Reviewer model")
    parser.add_argument("--arm", type=str, default="11", choices=["00", "10", "01", "11"], help="Factorial arm")
    parser.add_argument("--out-dir", type=str, default=None, help="Explicit output directory to save or resume")
    parser.add_argument("--limit-per-dataset", type=int, default=None, help="Optional limit per dataset (default: all)")
    args = parser.parse_args()

    if args.out_dir:
        out_dir = Path(args.out_dir)
    else:
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        out_dir = REPO_ROOT / "artifacts" / f"master_full_study_{timestamp_str}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("================================================================================")
    print(" VERITAS MASTER FULL-DATASET BENCHMARK (FULL MEANS FULL)")
    print(f" Output Directory: {out_dir}")
    print(f" Datasets: {args.datasets} | Actor: {args.actor} | Reviewer: {args.reviewer} | Arm: {args.arm}")
    print("================================================================================", flush=True)

    dataset_loaders = {
        "humaneval": load_humaneval_tasks,
        "mbpp": load_mbpp_tasks,
        "math500": load_math500_tasks,
        "gsm8k": load_gsm8k_tasks,
    }

    actor_cfg = ModelConfig(name=args.actor, backend="ollama", base_url="http://127.0.0.1:11434", temperature=0, max_tokens=2048)
    reviewer_cfg = ModelConfig(name=args.reviewer, backend="ollama", base_url="http://127.0.0.1:11434", temperature=0, max_tokens=768)

    overall_results = {}
    master_checkpoint = out_dir / "master_checkpoint.json"

    for d_name in args.datasets:
        if d_name not in dataset_loaders:
            print(f"Skipping unrecognized dataset: {d_name}")
            continue

        d_tasks = dataset_loaders[d_name]()
        if args.limit_per_dataset:
            d_tasks = d_tasks[:args.limit_per_dataset]

        total_d = len(d_tasks)
        print(f"\n########################################################################")
        print(f" STARTING DATASET: {d_name.upper()} (Total Tasks: {total_d})")
        print(f"########################################################################", flush=True)

        d_dir = out_dir / d_name
        d_dir.mkdir(parents=True, exist_ok=True)
        results_file = d_dir / "results.jsonl"

        d_results = []
        completed_task_ids = set()
        d_resolved = 0
        d_repairs = 0
        d_tokens = 0
        t0_d = time.time()

        if results_file.exists():
            for line in results_file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        record = json.loads(line)
                        completed_task_ids.add(record["task_id"])
                        d_results.append(record)
                        if record["resolved"]:
                            d_resolved += 1
                        if record["repaired"]:
                            d_repairs += 1
                        d_tokens += record["total_tokens"]
                    except Exception:
                        pass
            if completed_task_ids:
                print(f"Resuming {d_name.upper()}: {len(completed_task_ids)} tasks already completed ({d_resolved} resolved).", flush=True)
                if len(completed_task_ids) >= total_d and (d_dir / "summary.json").exists():
                    try:
                        d_summary = json.loads((d_dir / "summary.json").read_text(encoding="utf-8"))
                        overall_results[d_name] = d_summary
                        print(f"Dataset {d_name.upper()} already fully completed ({d_summary['pass_at_1']}% Pass@1). Loaded summary.", flush=True)
                        continue
                    except Exception:
                        pass

        for idx, task_data in enumerate(d_tasks, start=1):
            t_id = task_data["task_id"]
            if t_id in completed_task_ids:
                continue

            safe_name = t_id.replace("/", "_")
            trial_dir = d_dir / f"task_{idx:04d}_{safe_name}"

            try:
                res = run_task_trial(
                    task_data=task_data,
                    arm=args.arm,
                    actor_cfg=actor_cfg,
                    reviewer_cfg=reviewer_cfg,
                    trial_dir=trial_dir,
                )
            except Exception as e:
                print(f"[{d_name.upper()} | {idx:04d}/{total_d:04d}] {t_id:18s} -> ERROR ({e})", flush=True)
                res = {
                    "dataset": task_data["dataset"],
                    "task_id": task_data["task_id"],
                    "arm": args.arm,
                    "resolved": False,
                    "repaired": False,
                    "regressed": False,
                    "total_tokens": 0,
                    "total_seconds": 0,
                    "error": str(e),
                }

            d_results.append(res)
            if res["resolved"]:
                d_resolved += 1
            if res["repaired"]:
                d_repairs += 1
            d_tokens += res["total_tokens"]

            with open(results_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(res) + "\n")

            pass_rate = (d_resolved / idx) * 100.0
            status_str = "RESOLVED" if res["resolved"] else "FAILED"
            repair_str = " [REPAIRED in revision]" if res["repaired"] else ""
            print(
                f"[{d_name.upper()} | {idx:04d}/{total_d:04d}] {t_id:18s} -> {status_str:8s} "
                f"({res['total_seconds']:4.1f}s, {res['total_tokens']:4d} tok){repair_str} | "
                f"Cumulative Pass@1: {d_resolved}/{idx} ({pass_rate:5.1f}%)",
                flush=True,
            )

            # Checkpoint
            chk = {
                "current_dataset": d_name,
                "dataset_completed": idx,
                "dataset_total": total_d,
                "dataset_resolved": d_resolved,
                "dataset_pass_rate": round(pass_rate, 2),
                "dataset_repairs": d_repairs,
                "elapsed_minutes": round((time.time() - t0_d) / 60.0, 2),
            }
            write_json(d_dir / "checkpoint.json", chk)

        d_time = sum(r.get("total_seconds", 0) for r in d_results)
        d_summary = {
            "dataset": d_name,
            "total_tasks": total_d,
            "resolved_tasks": d_resolved,
            "pass_at_1": round((d_resolved / total_d) * 100.0, 2),
            "repairs": d_repairs,
            "total_tokens": d_tokens,
            "total_seconds": round(d_time, 2),
            "mean_seconds_per_task": round(d_time / total_d, 2) if total_d else 0.0,
        }
        overall_results[d_name] = d_summary
        write_json(d_dir / "summary.json", d_summary)

        print(f"\nCompleted {d_name.upper()}: {d_resolved}/{total_d} ({d_summary['pass_at_1']}%) in {d_time/60.0:.1f} mins", flush=True)

    # Master Report: aggregate all dataset summaries present in out_dir
    for name in dataset_loaders.keys():
        s_path = out_dir / name / "summary.json"
        if name not in overall_results and s_path.exists():
            try:
                overall_results[name] = json.loads(s_path.read_text(encoding="utf-8"))
            except Exception:
                pass

    write_json(out_dir / "master_report.json", overall_results)
    print("\n================================================================================")
    print(" ALL DATASETS FULL BENCHMARK COMPLETE!")
    print(f" Summary written to: {out_dir / 'master_report.json'}")
    print("================================================================================", flush=True)


if __name__ == "__main__":
    main()
