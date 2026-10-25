"""Reproducible Cross-Model Calibration Benchmark Harness.

Compares locally installed Ollama models on held-out repository bug-fix tasks:
- qwen2.5-coder:14b (Baseline)
- qwen2.5-coder:30b
- granite-code:20b
- deepseek-coder-v2:16b
- deepcoder:14b
- starcoder2:15b
- sqlcoder:15b (SQL-specialized subgroup)

Execution Conditions:
- In-process LocalSandbox (host execution with SHA-256 tree state hashing)
- Uniform frozen POLICY_SYSTEM prompt
- Sampling: temperature=0.0, max_tokens=2048
- Limits: steps=10, timeout=300s
- Zero evaluation awareness (D=0), zero reviewer feedback (A=0)
- Fresh isolated workspace for every trial
- Independent grader execution via pytest
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Enforce LocalSandbox
os.environ["VERITAS_LOCAL_SANDBOX"] = "1"
os.environ["VERITAS_SANDBOX_BACKEND"] = "local"
os.environ["VERITAS_NO_DOCKER"] = "1"

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from veritas.config import ModelConfig, SandboxConfig
from veritas.contracts import contract
from veritas.io import digest, write_json
from veritas.models import LocalModel
from veritas.runtime import AgentSession, run_phase
from veritas.sandbox import LocalSandbox, make_patch
from veritas.schema import Task
from veritas.state import tree_hash
from veritas.store import EventStore


# -----------------------------------------------------------------------------
# Held-Out Benchmark Task Definitions (Fresh & Untuned)
# -----------------------------------------------------------------------------

def setup_task_env_interpolator(ws: Path):
    """Task 1: Environment Variable Interpolator."""
    pkg = ws / "configkit"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .interpolator import interpolate_env\n', encoding="utf-8")

    code = '''"""Environment Variable Interpolator."""
import os
import re

def interpolate_env(template: str, env: dict = None) -> str:
    """Interpolate ${VAR} and ${VAR:-default} into template."""
    if env is None:
        env = dict(os.environ)

    def replace_var(match):
        expr = match.group(1).strip()
        if ":-" in expr:
            var_name, default_val = expr.split(":-", 1)
        else:
            var_name, default_val = expr, ""

        # BUG: Crashes with KeyError on missing variable when no default is given,
        # instead of expanding to empty string. Also ignores default when env val is empty string.
        if var_name in env:
            val = env[var_name]
            if val == "" and ":-" in expr:
                return default_val
            return str(val)
        elif ":-" in expr:
            return default_val
        else:
            raise KeyError(f"Environment variable '{var_name}' not set")

    return re.sub(r"\\$\\{([^}]+)\\}", replace_var, template)
'''
    (pkg / "interpolator.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''from configkit.interpolator import interpolate_env

def test_basic_interpolation():
    assert interpolate_env("http://${HOST}:${PORT}", {"HOST": "localhost", "PORT": "8080"}) == "http://localhost:8080"

def test_default_fallback_when_unset():
    assert interpolate_env("DB: ${DB_NAME:-app_dev}", {}) == "DB: app_dev"

def test_default_fallback_when_empty():
    assert interpolate_env("MODE=${MODE:-production}", {"MODE": ""}) == "MODE=production"

def test_missing_var_without_default():
    assert interpolate_env("Hello ${NAME}!", {}) == "Hello !"
'''
    (tests / "test_interpolator.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `configkit/interpolator.py`, fix `interpolate_env`: when a referenced variable is missing from `env` "
        "and no default is specified via `:-`, it should expand to an empty string `\"\"` instead of raising KeyError. "
        "Read the file with read_file, edit in-place with edit_file, test with run_tests, and submit final_answer."
    )
    return "configkit", prompt


def setup_task_schema_coercer(ws: Path):
    """Task 2: Type Coercion for Schema Fields."""
    pkg = ws / "schematools"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .coercer import coerce_value\n', encoding="utf-8")

    code = '''"""Type Coercion."""

def coerce_value(val, target_type: str):
    """Coerce string/primitive val to target_type ('int', 'float', 'bool', 'str')."""
    if val is None:
        return None
    if target_type == "str":
        return str(val)
    if target_type == "int":
        return int(val)
    if target_type == "float":
        return float(val)
    if target_type == "bool":
        # BUG: Direct bool(val) evaluates non-empty strings like 'false', '0', 'no' as True
        return bool(val)
    raise ValueError(f"Unknown target type: {target_type}")
'''
    (pkg / "coercer.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''from schematools.coercer import coerce_value

def test_coerce_int_and_float():
    assert coerce_value("42", "int") == 42
    assert coerce_value("3.14", "float") == 3.14

def test_coerce_bool_true():
    assert coerce_value("true", "bool") is True
    assert coerce_value("1", "bool") is True
    assert coerce_value("True", "bool") is True

def test_coerce_bool_false():
    assert coerce_value("false", "bool") is False
    assert coerce_value("0", "bool") is False
    assert coerce_value("False", "bool") is False
    assert coerce_value("no", "bool") is False
'''
    (tests / "test_coercer.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `schematools/coercer.py`, fix `coerce_value` for `target_type == 'bool'`: string literals "
        "`'false'`, `'0'`, `'no'`, `'False'` (case-insensitive) must evaluate to `False`, while `'true'`, `'1'`, `'yes'`, `'True'` evaluate to `True`. "
        "Read the file, edit in place with edit_file, test with run_tests, and submit final_answer."
    )
    return "schematools", prompt


def setup_task_topological_sorter(ws: Path):
    """Task 3: Topological Dependency Sorter with Cycle Detection."""
    pkg = ws / "graphlib"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .toposort import topological_sort, CycleError\n', encoding="utf-8")

    code = '''"""Topological Dependency Sorter."""

class CycleError(Exception):
    pass

def topological_sort(graph: dict) -> list:
    """Perform topological sort on DAG {node: [dependencies]}.
    Dependencies must appear before dependents in the returned order.
    """
    visited = set()
    order = []

    # BUG: Fails to distinguish recursion stack nodes from completed nodes,
    # falsely raising CycleError on diamond/convergent dependencies.
    def dfs(node):
        if node in visited:
            raise CycleError(f"Cycle detected involving {node}")
        visited.add(node)
        for dep in graph.get(node, []):
            dfs(dep)
        order.append(node)

    for n in sorted(graph.keys()):
        if n not in visited:
            dfs(n)
    return order
'''
    (pkg / "toposort.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''import pytest
from graphlib.toposort import topological_sort, CycleError

def test_linear_dependency():
    graph = {"build": ["compile"], "compile": ["source"], "source": []}
    res = topological_sort(graph)
    assert res.index("source") < res.index("compile") < res.index("build")

def test_diamond_dependency():
    graph = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
    res = topological_sort(graph)
    assert res.index("D") < res.index("B") < res.index("A")
    assert res.index("D") < res.index("C") < res.index("A")

def test_actual_cycle_raises():
    graph = {"A": ["B"], "B": ["C"], "C": ["A"]}
    with pytest.raises(CycleError):
        topological_sort(graph)
'''
    (tests / "test_toposort.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `graphlib/toposort.py`, fix `topological_sort`: distinguish visiting nodes (currently on the recursion stack) "
        "from fully visited nodes so that diamond/convergent DAG structures do not raise `CycleError`. Genuine cycles must still raise `CycleError`. "
        "Read the file, edit with edit_file, test with run_tests, and submit final_answer."
    )
    return "graphlib", prompt


def setup_task_router_matcher(ws: Path):
    """Task 4: URL Path Pattern Matcher."""
    pkg = ws / "routing"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .router import match_route\n', encoding="utf-8")

    code = '''"""URL Path Pattern Matcher."""
import re

def match_route(pattern: str, path: str):
    """Match URL route pattern (e.g. '/users/<int:id>/posts/<slug>') against path."""
    # BUG: Does not anchor regex with ^ and $, allowing partial matches,
    # and does not cast typed parameters like <int:name> to integers.
    regex_pattern = re.sub(r"<int:(\\w+)>", r"(?P<\\1>\\d+)", pattern)
    regex_pattern = re.sub(r"<(\\w+)>", r"(?P<\\1>[^/]+)", regex_pattern)

    match = re.search(regex_pattern, path)
    if not match:
        return None
    return match.groupdict()
'''
    (pkg / "router.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''from routing.router import match_route

def test_simple_match_with_int_conversion():
    res = match_route("/users/<int:user_id>", "/users/1024")
    assert res == {"user_id": 1024}
    assert isinstance(res["user_id"], int)

def test_slug_match():
    res = match_route("/posts/<slug>", "/posts/hello-world")
    assert res == {"slug": "hello-world"}

def test_exact_path_boundaries():
    assert match_route("/api/v1/status", "/api/v1/status/extra") is None
    assert match_route("/api/v1/status", "/prefix/api/v1/status") is None
'''
    (tests / "test_router.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `routing/router.py`, fix `match_route`: match the entire path from start to end (anchor with `^` and `$`), "
        "and cast `<int:...>` matched parameters to Python `int` values in the returned dictionary. "
        "Read the file, edit with edit_file, test with run_tests, and submit final_answer."
    )
    return "routing", prompt


def setup_task_constant_time_compare(ws: Path):
    """Task 5: Constant-Time Token Comparator."""
    pkg = ws / "cryptokit"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .compare import secure_compare\n', encoding="utf-8")

    code = '''"""Constant-Time Token Comparator."""

def secure_compare(val1: str, val2: str) -> bool:
    """Compare two authentication tokens securely."""
    # BUG: Converts both to lowercase and strips whitespace, causing false positives on case/whitespace
    if not isinstance(val1, str) or not isinstance(val2, str):
        return False
    return val1.strip().lower() == val2.strip().lower()
'''
    (pkg / "compare.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''from cryptokit.compare import secure_compare

def test_identical_match():
    assert secure_compare("SecretToken123", "SecretToken123") is True

def test_case_sensitivity():
    assert secure_compare("SecretToken", "secrettoken") is False

def test_whitespace_sensitivity():
    assert secure_compare("Token ", "Token") is False
    assert secure_compare(" Token", "Token") is False

def test_non_string():
    assert secure_compare(None, "Token") is False
'''
    (tests / "test_compare.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `cryptokit/compare.py`, fix `secure_compare`: tokens must be compared strictly with case-sensitivity "
        "and without stripping whitespace, returning True only if val1 and val2 are identical strings. "
        "Read the file, edit with edit_file, test with run_tests, and submit final_answer."
    )
    return "cryptokit", prompt


def setup_task_iso_duration(ws: Path):
    """Task 6: ISO 8601 Duration Parser."""
    pkg = ws / "timekit"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .duration import parse_iso_duration\n', encoding="utf-8")

    code = '''"""ISO 8601 Duration Parser."""
import re

def parse_iso_duration(duration_str: str) -> int:
    """Parse ISO 8601 duration string into total seconds."""
    # BUG: Requires both Days and Time parts (P...DT...), crashing when only time (PT...) or only days (P...D) is provided
    pattern = r"^P(\\d+)DT(?:(\\d+)H)?(?:(\\d+)M)?(?:(\\d+)S)?$"
    match = re.match(pattern, duration_str)
    if not match:
        raise ValueError(f"Invalid duration format: {duration_str}")
    days = int(match.group(1))
    hours = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = int(match.group(4) or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds
'''
    (pkg / "duration.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''import pytest
from timekit.duration import parse_iso_duration

def test_days_and_time():
    assert parse_iso_duration("P1DT2H30M") == 86400 + 7200 + 1800

def test_time_only():
    assert parse_iso_duration("PT1H") == 3600
    assert parse_iso_duration("PT45M") == 2700
    assert parse_iso_duration("PT30S") == 30

def test_days_only():
    assert parse_iso_duration("P2D") == 172800

def test_invalid_format():
    with pytest.raises(ValueError):
        parse_iso_duration("1 hour")
'''
    (tests / "test_duration.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `timekit/duration.py`, fix `parse_iso_duration`: parse durations with optional days (`P...D`) "
        "and optional time components (`T...H...M...S`), supporting time-only (e.g. `PT1H`, `PT30S`) and days-only (e.g. `P2D`) formats. "
        "Invalid strings must raise ValueError. Read the file, edit with edit_file, test with run_tests, and submit final_answer."
    )
    return "timekit", prompt


def setup_task_sql_builder(ws: Path):
    """Task 7: Parameterized SQL Query Builder (SQL Subgroup)."""
    pkg = ws / "sqltools"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .builder import build_select_query\n', encoding="utf-8")

    code = '''"""SQL Query Builder."""

def build_select_query(table: str, columns: list = None, filters: dict = None, order_by: str = None, limit: int = None, offset: int = None):
    """Build parameterized SELECT query string and parameter tuple."""
    cols = ", ".join(columns) if columns else "*"
    sql = f"SELECT {cols} FROM {table}"
    params = []

    if filters:
        # BUG: String concatenates filter values into SQL instead of using '?' placeholders
        where_clauses = []
        for k, v in filters.items():
            where_clauses.append(f"{k} = '{v}'")
        sql += " WHERE " + " AND ".join(where_clauses)

    if order_by:
        sql += f" ORDER BY {order_by}"

    if offset is not None:
        # BUG: Emits OFFSET before LIMIT (invalid syntax in SQLite)
        sql += f" OFFSET {offset}"

    if limit is not None:
        sql += f" LIMIT {limit}"

    return sql.strip(), tuple(params)
'''
    (pkg / "builder.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''import sqlite3
from sqltools.builder import build_select_query

def test_parameterized_where():
    query, params = build_select_query("users", columns=["id", "name"], filters={"status": "active", "role": "admin"})
    assert "WHERE status = ? AND role = ?" in query
    assert params == ("active", "admin")

def test_limit_and_offset_order():
    query, params = build_select_query("products", limit=10, offset=20)
    assert query.endswith("LIMIT 10 OFFSET 20")

def test_sqlite_execution():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE users (id INT, name TEXT, status TEXT, role TEXT)")
    con.execute("INSERT INTO users VALUES (1, 'Alice', 'active', 'admin')")
    con.execute("INSERT INTO users VALUES (2, 'Bob', 'inactive', 'user')")
    query, params = build_select_query("users", filters={"status": "active", "role": "admin"})
    rows = con.execute(query, params).fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "Alice"
'''
    (tests / "test_builder.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `sqltools/builder.py`, fix `build_select_query`: use `?` placeholders for WHERE filters and populate `params` tuple. "
        "Ensure `LIMIT` precedes `OFFSET` in the output SQL (e.g. `LIMIT 10 OFFSET 20`). "
        "Read the file, edit with edit_file, test with run_tests, and submit final_answer."
    )
    return "sqltools", prompt


GENERAL_TASKS = [
    ("env_var_interpolator", setup_task_env_interpolator),
    ("json_schema_coercer", setup_task_schema_coercer),
    ("topological_dependency_sorter", setup_task_topological_sorter),
    ("url_path_pattern_matcher", setup_task_router_matcher),
    ("constant_time_comparator", setup_task_constant_time_compare),
    ("iso_duration_parser", setup_task_iso_duration),
]

SQL_TASKS = [
    ("sql_query_builder", setup_task_sql_builder),
]

ALL_BENCHMARK_TASKS = GENERAL_TASKS + SQL_TASKS


# -----------------------------------------------------------------------------
# Diagnostic Evaluator & Single Trial Runner
# -----------------------------------------------------------------------------

@dataclass
class TrialResult:
    task_name: str
    model_name: str
    steps_taken: int
    tokens_consumed: int
    wall_clock_seconds: float
    valid_actions: bool
    file_edited: bool
    applicable_patch: bool
    tests_passed: bool
    grader_resolved: bool
    failure_mode: Optional[str] = None
    failure_detail: Optional[str] = None
    patch_size_chars: int = 0
    initial_tree_hash: str = ""
    final_tree_hash: str = ""


def evaluate_workspace(ws: Path) -> Tuple[bool, str]:
    """Run pytest suite inside the workspace."""
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=str(ws),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return res.returncode == 0, res.stdout + "\n" + res.stderr


def run_benchmark_trial(
    task_name: str,
    setup_fn,
    model_cfg: ModelConfig,
    trial_base_dir: Path,
) -> TrialResult:
    """Execute one model-task trial under frozen conditions."""
    trial_id = f"{task_name}_{model_cfg.name.replace(':', '_')}"
    trial_dir = trial_base_dir / trial_id
    if trial_dir.exists():
        shutil.rmtree(trial_dir)
    trial_dir.mkdir(parents=True, exist_ok=True)

    ws = trial_dir / "workspace"
    baseline = trial_dir / "baseline"

    pkg_name, prompt = setup_fn(ws)
    shutil.copytree(ws, baseline)

    init_tree = tree_hash(ws)

    # Sanity check: baseline test must fail
    pre_pass, _ = evaluate_workspace(ws)
    assert not pre_pass, f"Pre-test unexpectedly passed for {task_name}"

    sandbox_cfg = SandboxConfig(image="local", memory="2g", cpus=2, timeout_seconds=60, max_output_chars=5000)
    sandbox = LocalSandbox(ws, sandbox_cfg)
    model = LocalModel(model_cfg)

    task = Task(
        task_id=f"bench_{task_name}",
        group_id=f"group_{pkg_name}",
        source="model_calibration",
        source_revision="1" * 40,
        source_split="dev",
        kind="swe",
        prompt=prompt,
        official_holdout=False,
        repo=pkg_name,
        base_commit="a" * 40,
        private={"instance_id": task_name, "repo": pkg_name},
    )

    from types import SimpleNamespace
    protocol = SimpleNamespace(
        compact=False,
        history_chars=30000,
        observation_chars=2000,
        input_chars=60000,
        partition="development",
        sandbox=sandbox_cfg,
    )
    limits = SimpleNamespace(steps=10, completion_tokens=4096, seconds=300)

    session = AgentSession()
    event_store = EventStore(trial_dir / "events.sqlite")

    t0 = time.time()
    phase_res = run_phase(
        task=task,
        session=session,
        model=model,
        sandbox=sandbox,
        store=event_store,
        output=trial_dir,
        trial_id=trial_id,
        actor_name=model_cfg.name,
        phase="draft",
        limits=limits,
        protocol=protocol,
        cue="",
    )
    elapsed = time.time() - t0

    patch = make_patch(baseline, ws)
    (trial_dir / "final.patch").write_text(patch, encoding="utf-8")
    final_tree = tree_hash(ws)

    records = list(event_store.records())
    event_store.close()

    # Tier 1: Valid actions
    valid_actions = all(not r.blocked for r in records) and len(records) > 0

    # Tier 2: Source file edited
    changed_files = [line[6:].strip() for line in patch.splitlines() if line.startswith("+++ b/")]
    file_edited = any(f.startswith(pkg_name) and f.endswith(".py") for f in changed_files)

    # Tier 3: Applicable non-empty patch
    applicable_patch = len(patch.strip()) > 0

    # Tier 4 & 5: Tests passed and grader resolved
    test_passed, test_out = evaluate_workspace(ws)
    grader_resolved = test_passed and file_edited

    # Failure Mode Taxonomy
    failure_mode = None
    failure_detail = None
    if not valid_actions:
        blocked_reasons = [r.block_reason for r in records if r.blocked]
        failure_mode = "INVALID_OUTPUT"
        failure_detail = f"Blocked steps: {blocked_reasons}"
    elif not applicable_patch:
        failure_mode = "NO_EDITS"
        failure_detail = "Agent made zero modifications to files"
    elif not file_edited:
        failure_mode = "WRONG_FILE"
        failure_detail = f"Edited files outside package ({changed_files})"
    elif not test_passed:
        failure_mode = "TEST_FAILURE"
        failure_detail = f"Pytest failed:\n{test_out[:400]}"

    status_str = "RESOLVED" if grader_resolved else f"FAILED ({failure_mode})"
    print(f"  [{model_cfg.name:<22}] on [{task_name:<26}] -> {status_str} in {phase_res['steps']} steps ({elapsed:4.1f}s)")

    return TrialResult(
        task_name=task_name,
        model_name=model_cfg.name,
        steps_taken=phase_res["steps"],
        tokens_consumed=phase_res["known_completion_tokens"],
        wall_clock_seconds=elapsed,
        valid_actions=valid_actions,
        file_edited=file_edited,
        applicable_patch=applicable_patch,
        tests_passed=test_passed,
        grader_resolved=grader_resolved,
        failure_mode=failure_mode,
        failure_detail=failure_detail,
        patch_size_chars=len(patch),
        initial_tree_hash=init_tree,
        final_tree_hash=final_tree,
    )


# -----------------------------------------------------------------------------
# Statistical & Reporting Helpers
# -----------------------------------------------------------------------------

def wilson_interval(successes: int, total: int, z: float = 1.96) -> Tuple[float, float]:
    """Compute 95% Wilson score interval for binomial proportion."""
    if total == 0:
        return 0.0, 0.0
    p = successes / total
    denom = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denom
    return max(0.0, centre - spread), min(1.0, centre + spread)


def compute_paired_comparison(baseline_recs: List[TrialResult], model_recs: List[TrialResult]):
    """Compute wins, losses, ties against baseline for identical tasks."""
    base_map = {r.task_name: r.grader_resolved for r in baseline_recs}
    wins, losses, ties = 0, 0, 0
    for r in model_recs:
        if r.task_name in base_map:
            base_res = base_map[r.task_name]
            mod_res = r.grader_resolved
            if mod_res and not base_res:
                wins += 1
            elif not mod_res and base_res:
                losses += 1
            else:
                ties += 1
    return wins, losses, ties


# -----------------------------------------------------------------------------
# Main Benchmark Driver
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Reproducible Cross-Model Calibration Benchmark")
    parser.add_argument("--smoke", action="store_true", help="Run 1 smoke task per model before scaling")
    parser.add_argument("--model", type=str, default=None, help="Filter by model name substring")
    parser.add_argument("--task", type=str, default=None, help="Filter by task name substring")
    args = parser.parse_args()

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    out_dir = REPO_ROOT / "artifacts" / f"model_benchmark_{timestamp_str}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("================================================================================")
    print(" VERITAS CROSS-MODEL CODING CALIBRATION BENCHMARK")
    print(f" Output Directory: {out_dir}")
    print(f" Mode: {'SMOKE RUN (1 task/model)' if args.smoke else 'FULL HELD-OUT BENCHMARK'}")
    print("================================================================================")

    # Candidate Models Specification
    all_models = [
        ModelConfig(name="qwen2.5-coder:14b", backend="ollama", base_url="http://127.0.0.1:11434", temperature=0, max_tokens=2048),
        ModelConfig(name="qwen2.5-coder:30b", backend="ollama", base_url="http://127.0.0.1:11434", temperature=0, max_tokens=2048),
        ModelConfig(name="granite-code:20b", backend="ollama", base_url="http://127.0.0.1:11434", temperature=0, max_tokens=2048),
        ModelConfig(name="deepseek-coder-v2:16b", backend="ollama", base_url="http://127.0.0.1:11434", temperature=0, max_tokens=2048),
        ModelConfig(name="deepcoder:14b", backend="ollama", base_url="http://127.0.0.1:11434", temperature=0, max_tokens=2048),
        ModelConfig(name="starcoder2:15b", backend="ollama", base_url="http://127.0.0.1:11434", temperature=0, max_tokens=2048),
        ModelConfig(name="sqlcoder:15b", backend="ollama", base_url="http://127.0.0.1:11434", temperature=0, max_tokens=2048),
    ]

    selected_models = [m for m in all_models if args.model is None or args.model in m.name]

    results: List[TrialResult] = []

    for model_cfg in selected_models:
        is_sql_specialist = (model_cfg.name == "sqlcoder:15b")
        
        if args.smoke:
            # 1 smoke task per model
            tasks_for_model = [SQL_TASKS[0]] if is_sql_specialist else [GENERAL_TASKS[0]]
        else:
            # Full benchmark
            tasks_for_model = SQL_TASKS if is_sql_specialist else ALL_BENCHMARK_TASKS

        if args.task:
            tasks_for_model = [t for t in tasks_for_model if args.task in t[0]]

        print(f"\n>>> Running Model: {model_cfg.name} ({len(tasks_for_model)} tasks) <<<")
        for task_name, setup_fn in tasks_for_model:
            res = run_benchmark_trial(task_name, setup_fn, model_cfg, out_dir)
            results.append(res)

    # -------------------------------------------------------------------------
    # Evaluation Reporting & Summary Generation
    # -------------------------------------------------------------------------
    print("\n================================================================================")
    print(" BENCHMARK OUTCOME MATRIX")
    print("================================================================================")
    header = f"{'Model':<22} | {'Task':<26} | {'Valid':<5} | {'Edit':<5} | {'Patch':<5} | {'Test':<5} | {'Res':<5} | {'Sec':<5} | {'Status'}"
    print(header)
    print("-" * len(header))
    for r in results:
        status = "CLEAN" if r.grader_resolved else (r.failure_mode or "FAILED")
        print(f"{r.model_name:<22} | {r.task_name:<26} | {str(r.valid_actions):<5} | {str(r.file_edited):<5} | {str(r.applicable_patch):<5} | {str(r.tests_passed):<5} | {str(r.grader_resolved):<5} | {r.wall_clock_seconds:<5.1f} | {status}")

    # Summary by model
    print("\n================================================================================")
    print(" MODEL PERFORMANCE SUMMARY & PAIRED COMPARISON VS BASELINE")
    print("================================================================================")

    baseline_name = "qwen2.5-coder:14b"
    baseline_recs = [r for r in results if r.model_name == baseline_name]

    summary_data = []

    for m in selected_models:
        m_recs = [r for r in results if r.model_name == m.name]
        n = len(m_recs)
        if n == 0:
            continue

        resolved_count = sum(r.grader_resolved for r in m_recs)
        res_rate = resolved_count / n * 100
        ci_low, ci_high = wilson_interval(resolved_count, n)

        valid_rate = sum(r.valid_actions for r in m_recs) / n * 100
        edit_rate = sum(r.file_edited for r in m_recs) / n * 100
        patch_rate = sum(r.applicable_patch for r in m_recs) / n * 100
        test_rate = sum(r.tests_passed for r in m_recs) / n * 100

        tokens = [r.tokens_consumed for r in m_recs]
        steps = [r.steps_taken for r in m_recs]
        secs = [r.wall_clock_seconds for r in m_recs]

        med_tokens = sorted(tokens)[len(tokens) // 2]
        med_steps = sorted(steps)[len(steps) // 2]
        med_secs = sorted(secs)[len(secs) // 2]

        wins, losses, ties = compute_paired_comparison(baseline_recs, m_recs)

        print(f"\nModel: {m.name} (N = {n} Tasks):")
        print(f"  Resolution Rate (Tier 5) : {res_rate:5.1f}% ({resolved_count}/{n}) [95% CI: {ci_low*100:.1f}% - {ci_high*100:.1f}%]")
        print(f"  Valid Action Rate (Tier 1): {valid_rate:5.1f}%")
        print(f"  File Edited Rate (Tier 2) : {edit_rate:5.1f}%")
        print(f"  Applicable Patch (Tier 3) : {patch_rate:5.1f}%")
        print(f"  Unit Test Pass (Tier 4)   : {test_rate:5.1f}%")
        print(f"  Paired vs {baseline_name:<15}: Wins: {wins} | Losses: {losses} | Ties: {ties}")
        print(f"  Medians [Tokens / Steps / Sec]: {med_tokens} tok / {med_steps} stp / {med_secs:.1f}s (Tokens range: [{min(tokens)}, {max(tokens)}])")

        summary_data.append({
            "model": m.name,
            "tasks_attempted": n,
            "resolved": resolved_count,
            "resolution_rate_pct": round(res_rate, 2),
            "wilson_ci_95": [round(ci_low * 100, 2), round(ci_high * 100, 2)],
            "tier1_valid_rate": round(valid_rate, 2),
            "tier2_edit_rate": round(edit_rate, 2),
            "tier3_patch_rate": round(patch_rate, 2),
            "tier4_test_rate": round(test_rate, 2),
            "paired_vs_baseline": {"wins": wins, "losses": losses, "ties": ties},
            "tokens_median": med_tokens,
            "tokens_range": [min(tokens), max(tokens)],
            "steps_median": med_steps,
            "seconds_median": round(med_secs, 2),
        })

    # Save detailed JSON report
    report_file = out_dir / "benchmark_report.json"
    write_json(report_file, {
        "timestamp": timestamp_str,
        "baseline_model": baseline_name,
        "models": [m.name for m in selected_models],
        "summary": summary_data,
        "trials": [
            {
                "task": r.task_name,
                "model": r.model_name,
                "resolved": r.grader_resolved,
                "tests_passed": r.tests_passed,
                "applicable_patch": r.applicable_patch,
                "file_edited": r.file_edited,
                "valid_actions": r.valid_actions,
                "failure_mode": r.failure_mode,
                "failure_detail": r.failure_detail,
                "steps": r.steps_taken,
                "tokens": r.tokens_consumed,
                "seconds": round(r.wall_clock_seconds, 2),
                "patch_size": r.patch_size_chars,
                "initial_tree_hash": r.initial_tree_hash,
                "final_tree_hash": r.final_tree_hash,
            }
            for r in results
        ],
    })
    print(f"\nDetailed JSON Report saved to: {report_file}")
    print("================================================================================")


if __name__ == "__main__":
    main()
