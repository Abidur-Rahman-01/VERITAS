"""
run_action_time_tse_experiment.py

Executable IEEE TSE Action-Time Runtime Verification Experiment Runner.
Executes the unified 3-arm comparative matrix on pinned repository repair tasks:
  Arm 0: Unverified Baseline Control (policy: 'never', budget: 0.0, step cap: 30)
  Arm 1: Budget-Matched Random Verification (policy: 'random', threshold: 0.33, budget: 0.4, step cap: 30)
  Arm 2: Selective Action-Time Verification Gate (policy: 'error_impact', threshold: 0.25, budget: 0.4, step cap: 30)

Records all action proposals, verifier decisions (decision='verify'), verifier verdicts,
blocked states (blocked=True), and states before/after to events.sqlite.
Independently grades each final workspace via pytest.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Enforce local sandbox execution
os.environ["VERITAS_LOCAL_SANDBOX"] = "1"
os.environ["VERITAS_SANDBOX_BACKEND"] = "local"
os.environ["VERITAS_NO_DOCKER"] = "1"

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from veritas.config import Config, load_config
from veritas.models import LocalModel
from veritas.runtime import run_task
from veritas.sandbox import LocalSandbox
from veritas.schema import Task, Usage, Verification
from veritas.state import tree_hash
from veritas.store import EventStore
from veritas.verifier import Verifier

# Import task setup fixtures from model comparison benchmark
from scripts.run_model_comparison_benchmark import (
    setup_task_env_interpolator,
    setup_task_schema_coercer,
    setup_task_topological_sorter,
    setup_task_router_matcher,
    setup_task_constant_time_compare,
    setup_task_iso_duration,
    setup_task_sql_builder,
    evaluate_workspace,
)


def setup_task_csv_validator(ws: Path) -> tuple[str, str]:
    """Setup a CSV delimiter validator repository bug."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "csv_validator"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "validator.py").write_text(
        '"""CSV delimiter and field validator."""\n\n'
        "def split_csv_line(line: str, delimiter: str = ',') -> list[str]:\n"
        "    # BUG: Naive split fails on quoted fields with embedded delimiters\n"
        "    return line.strip().split(delimiter)\n"
    )

    (tests / "test_csv.py").write_text(
        "import pytest\n"
        "from csv_validator.validator import split_csv_line\n\n"
        "def test_simple_split():\n"
        "    assert split_csv_line('a,b,c') == ['a', 'b', 'c']\n\n"
        "def test_quoted_split():\n"
        "    assert split_csv_line('\"a,b\",c') == ['\"a,b\"', 'c']\n\n"
        "def test_semicolon_split():\n"
        "    assert split_csv_line('1;2;3', delimiter=';') == ['1', '2', '3']\n"
    )

    prompt = (
        "Repository csv_validator has a bug: `split_csv_line` in csv_validator/validator.py fails when fields contain "
        "quoted delimiters (e.g. '\"a,b\",c' should return ['\"a,b\"', 'c']). "
        "Fix the implementation using csv parsing or quote awareness so all tests in tests/test_csv.py pass. "
        "Do not break tests/test_csv.py. Submit final_answer when done."
    )
    return "csv_validator", prompt


def setup_task_cli_engine(ws: Path) -> tuple[str, str]:
    """Setup a CLI flag parser engine repository bug."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "cli_engine"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "parser.py").write_text(
        '"""Command line short flag parser."""\n\n'
        "def parse_flags(argv: list[str]) -> dict[str, bool]:\n"
        "    flags = {}\n"
        "    for arg in argv:\n"
        "        if arg.startswith('-') and not arg.startswith('--'):\n"
        "            # BUG: only handles single character flag, e.g. -v, fails on combined -xvf\n"
        "            flags[arg[1:]] = True\n"
        "    return flags\n"
    )

    (tests / "test_flags.py").write_text(
        "import pytest\n"
        "from cli_engine.parser import parse_flags\n\n"
        "def test_single_flag():\n"
        "    assert parse_flags(['-v']) == {'v': True}\n\n"
        "def test_combined_flags():\n"
        "    assert parse_flags(['-xvf']) == {'x': True, 'v': True, 'f': True}\n\n"
        "def test_multiple_args():\n"
        "    assert parse_flags(['-a', '-bc']) == {'a': True, 'b': True, 'c': True}\n"
    )

    prompt = (
        "Repository cli_engine has a bug: `parse_flags` in cli_engine/parser.py fails on combined short flags "
        "(e.g. '-xvf' should produce flags 'x', 'v', 'f' as True). "
        "Modify cli_engine/parser.py so that all tests in tests/test_flags.py pass. Submit final_answer when complete."
    )
    return "cli_engine", prompt


def setup_swe_cmd2_744(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 744: python-cmd2/cmd2 history file directory creation."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "cmd2"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "cmd2.py").write_text(
        '"""Command line framework."""\nimport os\n\n'
        "class Cmd:\n"
        "    def __init__(self, history_file='history.txt'):\n"
        "        self.history_file = history_file\n\n"
        "    def _read_history(self):\n"
        "        # BUG: Fails when directory does not exist instead of creating it\n"
        "        if not os.path.exists(self.history_file):\n"
        "            return []\n"
        "        with open(self.history_file, 'r', encoding='utf-8') as f:\n"
        "            return [l.strip() for l in f.readlines()]\n\n"
        "    def _write_history(self, lines):\n"
        "        # BUG: Crashes if directory does not exist\n"
        "        with open(self.history_file, 'w', encoding='utf-8') as f:\n"
        "            for l in lines:\n"
        "                f.write(l + '\\n')\n"
    )

    (tests / "test_history.py").write_text(
        "import os\nimport pytest\nfrom cmd2.cmd2 import Cmd\n\n"
        "def test_history_in_nested_dir(tmp_path):\n"
        "    nested = tmp_path / 'nonexistent' / 'nested' / 'hist.txt'\n"
        "    cmd = Cmd(history_file=str(nested))\n"
        "    # Must not crash when writing to uncreated directory\n"
        "    cmd._write_history(['hello', 'world'])\n"
        "    assert nested.exists()\n"
        "    assert cmd._read_history() == ['hello', 'world']\n"
    )

    prompt = (
        "In `cmd2/cmd2.py`, fix `Cmd._write_history` so that if the parent directory of `self.history_file` "
        "does not exist, it is created automatically (e.g. using `os.makedirs(os.path.dirname(...), exist_ok=True)`). "
        "Ensure all tests in tests/test_history.py pass cleanly. Submit final_answer when done."
    )
    return "cmd2", prompt


def setup_swe_sympy_19512(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 19512: sympy/sympy Float comparison in polytools."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "sympy"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "polytools.py").write_text(
        '"""Symbolic polynomial tools."""\n\n'
        "def poly_compare(val1, val2, precision=1e-7):\n"
        "    # BUG: Fails on comparing float to int with exact precision bounds\n"
        "    if isinstance(val1, float) or isinstance(val2, float):\n"
        "        return abs(float(val1) - float(val2)) < precision\n"
        "    return val1 == val2\n"
    )

    (tests / "test_poly.py").write_text(
        "from sympy.polytools import poly_compare\n\n"
        "def test_exact_integers():\n"
        "    assert poly_compare(1, 1) is True\n"
        "    assert poly_compare(1, 2) is False\n\n"
        "def test_float_precision():\n"
        "    assert poly_compare(1.0, 1) is True\n"
        "    assert poly_compare(1.00000001, 1.0) is True\n"
    )

    prompt = (
        "In `sympy/polytools.py`, fix `poly_compare` to handle mixed float and int symbolic comparison "
        "accurately within the given precision. Ensure tests in tests/test_poly.py pass."
    )
    return "sympy", prompt


TASK_REGISTRY = {
    "repo_env_var_interpolator": setup_task_env_interpolator,
    "repo_json_schema_coercer": setup_task_schema_coercer,
    "repo_topological_sorter": setup_task_topological_sorter,
    "repo_url_router": setup_task_router_matcher,
    "repo_constant_time_compare": setup_task_constant_time_compare,
    "repo_iso_duration": setup_task_iso_duration,
    "repo_sql_query_builder": setup_task_sql_builder,
    "repo_csv_schema_validator": setup_task_csv_validator,
    "repo_cli_parser_engine": setup_task_cli_engine,
    "swe_cmd2_744": setup_swe_cmd2_744,
    "swe_sympy_19512": setup_swe_sympy_19512,
}

ARM_CONFIGS = {
    "arm0_unverified": REPO_ROOT / "configs" / "action_time_arm0_unverified.yaml",
    "arm1_random": REPO_ROOT / "configs" / "action_time_arm1_random.yaml",
    "arm2_selective": REPO_ROOT / "configs" / "action_time_arm2_action_time_gate.yaml",
}


def run_single_arm_task(
    arm: str,
    task_id: str,
    setup_fn,
    output_root: Path,
) -> dict:
    trial_id = f"{arm}_{task_id}"
    trial_dir = output_root / arm / task_id
    if trial_dir.exists():
        shutil.rmtree(trial_dir)
    trial_dir.mkdir(parents=True, exist_ok=True)

    ws_dir = trial_dir / "workspace"
    baseline_dir = trial_dir / "baseline"
    pkg_name, prompt = setup_fn(ws_dir)
    shutil.copytree(ws_dir, baseline_dir)

    cfg_file = ARM_CONFIGS[arm]
    cfg = load_config(cfg_file)

    actor_model = LocalModel(cfg.model)
    verifier_model = LocalModel(cfg.verifier) if arm != "arm0_unverified" else None
    verifier = Verifier(verifier_model, cfg.sandbox, probes=[["pytest", "tests/", "-q"]]) if verifier_model else None

    critic = actor_model
    sandbox = LocalSandbox(ws_dir, cfg.sandbox)
    store_file = trial_dir / "events.sqlite"
    store = EventStore(store_file)

    task_obj = Task(
        task_id=task_id,
        group_id="tse_action_time_group",
        source="repository_repair",
        source_revision="pinned_tse",
        source_split="test",
        kind="swe",
        prompt=prompt,
        official_holdout=True,
    )

    assignment = {
        "split": "test",
        "arm": arm,
        "calibration_role": "action_time_eval",
    }

    start_time = time.monotonic()
    runtime_summary = run_task(
        task=task_obj,
        assignment=assignment,
        config=cfg,
        policy=actor_model,
        critic=critic,
        verifier=verifier,
        sandbox=sandbox,
        store=store,
        output=trial_dir,
    )
    elapsed = time.monotonic() - start_time
    store.close()

    # Independent grading via pytest execution
    grade_log_file = trial_dir / "grade.log"
    grade_proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=ws_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    grade_log_file.write_text(f"Exit code: {grade_proc.returncode}\n\nSTDOUT:\n{grade_proc.stdout}\n\nSTDERR:\n{grade_proc.stderr}")
    resolved = (grade_proc.returncode == 0)

    # Inspect events database to verify logged records
    import sqlite3
    conn = sqlite3.connect(store_file)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM events")
    total_events = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM events WHERE json_extract(payload, '$.decision')='verify'")
    verified_decisions = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM events WHERE json_extract(payload, '$.blocked')=1 OR json_extract(payload, '$.blocked')=true")
    blocked_actions = c.fetchone()[0]
    conn.close()

    result = {
        "trial_id": trial_id,
        "arm": arm,
        "task_id": task_id,
        "resolved": resolved,
        "elapsed_seconds": round(elapsed, 2),
        "total_events": total_events,
        "verified_decisions": verified_decisions,
        "blocked_actions": blocked_actions,
        "steps_completed": runtime_summary.get("steps_completed", 0),
        "policy_tokens": runtime_summary.get("total_online_tokens", 0),
        "verifier_spent": runtime_summary.get("verification_spent", 0.0),
    }

    (trial_dir / "summary.json").write_text(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description="Run Action-Time Verification Experiment")
    parser.add_argument("--arms", default="arm0_unverified,arm1_random,arm2_selective", help="Comma-separated arms")
    parser.add_argument("--tasks", type=int, default=len(TASK_REGISTRY), help="Number of tasks to run")
    parser.add_argument("--output", default="artifacts/action_time_study", help="Output directory")
    args = parser.parse_args()

    out_dir = REPO_ROOT / args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    arms = [a.strip() for a in args.arms.split(",")]
    task_keys = list(TASK_REGISTRY.keys())[:args.tasks]

    print(f"=== Starting Action-Time Verification Experiment ===")
    print(f"Arms: {arms}")
    print(f"Tasks ({len(task_keys)}): {task_keys}")
    print(f"Output: {out_dir}\n")

    results = []
    for task_id in task_keys:
        setup_fn = TASK_REGISTRY[task_id]
        for arm in arms:
            print(f"Running [{arm}] on [{task_id}]...")
            res = run_single_arm_task(arm, task_id, setup_fn, out_dir)
            print(f"  -> Resolved: {res['resolved']} | Verified Decisions: {res['verified_decisions']} | Blocked: {res['blocked_actions']} | Time: {res['elapsed_seconds']}s")
            results.append(res)

    # Master report
    report_file = out_dir / "action_time_report.json"
    report_file.write_text(json.dumps(results, indent=2))

    print("\n=== Experiment Complete ===")
    print(f"Report written to: {report_file}")


if __name__ == "__main__":
    main()
