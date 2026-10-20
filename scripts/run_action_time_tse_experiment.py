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


def setup_swe_cmd2_755(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 755: python-cmd2/cmd2 quoted redirect symbols in custom parser."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "cmd2"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "parsing.py").write_text(
        '"""Command line parser."""\n\n'
        "def parse_command_line(cmd: str) -> tuple[str, str | None]:\n"
        "    # BUG: Naive split on '>' splits redirect symbols inside quotes\n"
        "    if '>' in cmd:\n"
        "        parts = cmd.split('>', 1)\n"
        "        return parts[0].strip(), parts[1].strip()\n"
        "    return cmd.strip(), None\n"
    )

    (tests / "test_parsing.py").write_text(
        "import pytest\n"
        "from cmd2.parsing import parse_command_line\n\n"
        "def test_simple_redirect():\n"
        "    cmd, redir = parse_command_line('echo hello > out.txt')\n"
        "    assert cmd == 'echo hello'\n"
        "    assert redir == 'out.txt'\n\n"
        "def test_quoted_redirect_not_split():\n"
        "    cmd, redir = parse_command_line('echo \"hello > world\"')\n"
        "    assert cmd == 'echo \"hello > world\"'\n"
        "    assert redir is None\n"
    )

    prompt = (
        "In `cmd2/parsing.py`, fix `parse_command_line` so that redirection symbol `>` is ignored "
        "if it appears inside single or double quotes. Ensure tests in tests/test_parsing.py pass cleanly. Submit final_answer when done."
    )
    return "cmd2", prompt


def setup_swe_cmd2_760(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 760: python-cmd2/cmd2 subcommand argument completion."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "cmd2"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "completion.py").write_text(
        '"""Subcommand completion."""\n\n'
        "def complete_subcommand(subcommands: list[str], text: str) -> list[str]:\n"
        "    # BUG: Returns empty list when text is empty instead of returning all subcommands\n"
        "    if not text:\n"
        "        return []\n"
        "    return [s for s in subcommands if s.startswith(text)]\n"
    )

    (tests / "test_completion.py").write_text(
        "import pytest\n"
        "from cmd2.completion import complete_subcommand\n\n"
        "def test_prefix_matching():\n"
        "    assert complete_subcommand(['start', 'stop', 'status'], 'st') == ['start', 'stop', 'status']\n"
        "    assert complete_subcommand(['start', 'stop', 'status'], 'sto') == ['stop']\n\n"
        "def test_empty_text_all_candidates():\n"
        "    assert complete_subcommand(['start', 'stop'], '') == ['start', 'stop']\n"
    )

    prompt = (
        "In `cmd2/completion.py`, fix `complete_subcommand` so that when `text` is empty \"\", "
        "it returns the full list of available subcommands rather than an empty list. "
        "Ensure all tests in tests/test_completion.py pass. Submit final_answer when complete."
    )
    return "cmd2", prompt


def setup_swe_cmd2_770(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 770: python-cmd2/cmd2 colored output respects NO_COLOR environment."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "cmd2"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "ansi.py").write_text(
        '"""ANSI terminal styling."""\nimport os\n\n'
        "def colorize(text: str, color_code: str = '32') -> str:\n"
        "    # BUG: Does not inspect os.environ.get('NO_COLOR')\n"
        "    return f'\\033[{color_code}m{text}\\033[0m'\n"
    )

    (tests / "test_ansi.py").write_text(
        "import os\nimport pytest\nfrom cmd2.ansi import colorize\n\n"
        "def test_standard_colorize():\n"
        "    assert colorize('ok', '32') == '\\033[32mok\\033[0m'\n\n"
        "def test_no_color_environment(monkeypatch):\n"
        "    monkeypatch.setenv('NO_COLOR', '1')\n"
        "    assert colorize('ok', '32') == 'ok'\n"
    )

    prompt = (
        "In `cmd2/ansi.py`, modify `colorize` to check `os.environ.get('NO_COLOR')`. If NO_COLOR is set "
        "to a non-empty string, return `text` unchanged without ANSI escape sequences. "
        "Ensure tests in tests/test_ansi.py pass. Submit final_answer when complete."
    )
    return "cmd2", prompt


def setup_swe_cmd2_780(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 780: python-cmd2/cmd2 preserve multiline transcript state on abort."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "cmd2"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "transcript.py").write_text(
        '"""Transcript recording session."""\n\n'
        "class Transcript:\n"
        "    def __init__(self):\n"
        "        self.history = []\n"
        "        self.active_buffer = []\n\n"
        "    def record(self, cmd: str):\n"
        "        self.history.append(cmd)\n\n"
        "    def abort(self):\n"
        "        # BUG: Clears history along with active_buffer\n"
        "        self.history.clear()\n"
        "        self.active_buffer.clear()\n"
    )

    (tests / "test_transcript.py").write_text(
        "import pytest\nfrom cmd2.transcript import Transcript\n\n"
        "def test_record_commands():\n"
        "    t = Transcript()\n"
        "    t.record('cmd 1')\n"
        "    assert t.history == ['cmd 1']\n\n"
        "def test_abort_preserves_committed_history():\n"
        "    t = Transcript()\n"
        "    t.record('cmd 1')\n"
        "    t.active_buffer.append('partial')\n"
        "    t.abort()\n"
        "    assert t.history == ['cmd 1']\n"
        "    assert t.active_buffer == []\n"
    )

    prompt = (
        "In `cmd2/transcript.py`, fix `Transcript.abort` so that aborting only clears `active_buffer`, "
        "preserving previously committed commands in `self.history`. Ensure tests in tests/test_transcript.py pass."
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
        "    # BUG: Naive strict equality fails when comparing float approximations\n"
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
        "accurately within the given precision: `abs(float(val1) - float(val2)) < precision`. Ensure tests in tests/test_poly.py pass."
    )
    return "sympy", prompt


def setup_swe_sympy_20967(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 20967: sympy/sympy polynomial factorization on rational matrices."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "sympy"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "factortools.py").write_text(
        '"""Polynomial factorization tools."""\n\n'
        "def factor_rational_matrix_diag(mat: list[list[float]]) -> list[float]:\n"
        "    # BUG: Fails on zero elements on diagonal with ZeroDivisionError\n"
        "    diag = []\n"
        "    for i in range(len(mat)):\n"
        "        val = mat[i][i]\n"
        "        diag.append(1.0 / (1.0 / val))\n"
        "    return diag\n"
    )

    (tests / "test_factortools.py").write_text(
        "import pytest\nfrom sympy.factortools import factor_rational_matrix_diag\n\n"
        "def test_factor_nonzero_diag():\n"
        "    assert factor_rational_matrix_diag([[2.0, 0.0], [0.0, 4.0]]) == [2.0, 4.0]\n\n"
        "def test_factor_diag_with_zero():\n"
        "    assert factor_rational_matrix_diag([[0.0, 1.0], [1.0, 3.0]]) == [0.0, 3.0]\n"
    )

    prompt = (
        "In `sympy/factortools.py`, fix `factor_rational_matrix_diag` so that diagonal elements equal to 0.0 "
        "are safely returned as 0.0 without ZeroDivisionError. Ensure tests in tests/test_factortools.py pass cleanly."
    )
    return "sympy", prompt


def setup_swe_sympy_18033(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 18033: sympy/sympy prevent recursion loop in expression expansion."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "sympy"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "expand.py").write_text(
        '"""Expression expansion engine."""\n\n'
        "def expand_nested(expr: dict, depth: int = 0, max_depth: int = 4) -> dict:\n"
        "    # BUG: Recursion does not increment depth (passes depth instead of depth + 1)\n"
        "    if depth >= max_depth:\n"
        "        return {'_truncated': True}\n"
        "    res = {}\n"
        "    for k, v in expr.items():\n"
        "        if isinstance(v, dict):\n"
        "            res[k] = expand_nested(v, depth=depth, max_depth=max_depth)\n"
        "        else:\n"
        "            res[k] = v\n"
        "    return res\n"
    )

    (tests / "test_expand.py").write_text(
        "import pytest\nfrom sympy.expand import expand_nested\n\n"
        "def test_flat_dict():\n"
        "    assert expand_nested({'a': 1}) == {'a': 1}\n\n"
        "def test_deeply_nested_bounded():\n"
        "    nested = {'x': {'x': {'x': {'x': {'x': 1}}}}}\n"
        "    res = expand_nested(nested, depth=0, max_depth=3)\n"
        "    assert res['x']['x']['x'] == {'_truncated': True}\n"
    )

    prompt = (
        "In `sympy/expand.py`, fix `expand_nested` so that recursive calls pass `depth + 1` rather than `depth`, "
        "ensuring max_depth cutoff properly terminates deep structures. Ensure tests in tests/test_expand.py pass."
    )
    return "sympy", prompt


def setup_swe_sympy_18189(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 18189: sympy/sympy diophantine solver for quadratic forms."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "sympy"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "diophantine.py").write_text(
        '"""Diophantine equation solver."""\nimport math\n\n'
        "def solve_diophantine_quadratic(a: int, b: int, c: int) -> list[int]:\n"
        "    # BUG: Crashes with ValueError on negative discriminant instead of returning empty list []\n"
        "    disc = b * b - 4 * a * c\n"
        "    root = math.isqrt(disc)\n"
        "    if root * root != disc:\n"
        "        return []\n"
        "    roots = []\n"
        "    for sign in (1, -1):\n"
        "        num = -b + sign * root\n"
        "        if num % (2 * a) == 0:\n"
        "            roots.append(num // (2 * a))\n"
        "    return sorted(list(set(roots)))\n"
    )

    (tests / "test_diophantine.py").write_text(
        "import pytest\nfrom sympy.diophantine import solve_diophantine_quadratic\n\n"
        "def test_solvable_quadratic():\n"
        "    assert solve_diophantine_quadratic(1, -5, 6) == [2, 3]\n\n"
        "def test_negative_discriminant_returns_empty():\n"
        "    assert solve_diophantine_quadratic(1, 0, 1) == []\n"
    )

    prompt = (
        "In `sympy/diophantine.py`, fix `solve_diophantine_quadratic` so that when discriminant `disc < 0`, "
        "it returns `[]` immediately instead of crashing on `math.isqrt`. Ensure tests in tests/test_diophantine.py pass."
    )
    return "sympy", prompt


def setup_swe_sympy_18621(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 18621: sympy/sympy matrix exponential for degenerate eigenvalues."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "sympy"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "matrices.py").write_text(
        '"""Matrix exponential algorithms."""\n\n'
        "def matrix_exp_2x2(mat: list[list[float]]) -> list[list[float]]:\n"
        "    # BUG: Naive diagonal formula divides by difference of eigenvalues; for degenerate eigenvalues (l1 == l2), raises ZeroDivisionError\n"
        "    a, b = mat[0][0], mat[0][1]\n"
        "    c, d = mat[1][0], mat[1][1]\n"
        "    tr = a + d\n"
        "    det = a * d - b * c\n"
        "    diff = ((tr * tr / 4.0) - det) ** 0.5\n"
        "    l1 = tr / 2.0 + diff\n"
        "    l2 = tr / 2.0 - diff\n"
        "    inv = 1.0 / (l1 - l2)\n"
        "    return [[l1, 0.0], [0.0, l2]]\n"
    )

    (tests / "test_matrices.py").write_text(
        "import pytest\nfrom sympy.matrices import matrix_exp_2x2\n\n"
        "def test_distinct_eigenvalues():\n"
        "    res = matrix_exp_2x2([[2.0, 0.0], [0.0, 3.0]])\n"
        "    assert res is not None\n\n"
        "def test_degenerate_eigenvalues():\n"
        "    # Identity matrix has degenerate eigenvalues l1 == l2 == 1.0\n"
        "    res = matrix_exp_2x2([[1.0, 0.0], [0.0, 1.0]])\n"
        "    assert res == [[1.0, 0.0], [0.0, 1.0]]\n"
    )

    prompt = (
        "In `sympy/matrices.py`, fix `matrix_exp_2x2`: when eigenvalues are degenerate (`l1 == l2` or `abs(l1 - l2) < 1e-9`), "
        "handle the degeneracy without ZeroDivisionError (e.g. if `abs(l1 - l2) < 1e-9`, return `[[l1, 0.0], [0.0, l2]]`). "
        "Ensure tests in tests/test_matrices.py pass. Submit final_answer when done."
    )
    return "sympy", prompt


def setup_swe_pennylane_5063(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 5063: PennyLaneAI/pennylane device dispatch for custom adjoint operators."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "pennylane"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "devices.py").write_text(
        '"""Quantum hardware device dispatch."""\n\n'
        "def dispatch_adjoint(op_name: str) -> str:\n"
        "    supported = {'PauliX': 'kernel_x', 'PauliY': 'kernel_y', 'Hadamard': 'kernel_h'}\n"
        "    # BUG: Fails on 'Adjoint_' prefix instead of stripping it and returning kernel with adjoint suffix\n"
        "    return supported[op_name]\n"
    )

    (tests / "test_devices.py").write_text(
        "import pytest\nfrom pennylane.devices import dispatch_adjoint\n\n"
        "def test_base_dispatch():\n"
        "    assert dispatch_adjoint('PauliX') == 'kernel_x'\n\n"
        "def test_adjoint_dispatch():\n"
        "    assert dispatch_adjoint('Adjoint_PauliX') == 'kernel_x_adjoint'\n"
    )

    prompt = (
        "In `pennylane/devices.py`, update `dispatch_adjoint` so that if `op_name` starts with 'Adjoint_', "
        "it strips the prefix, looks up the base kernel, and returns f'{base_kernel}_adjoint'. "
        "Ensure tests in tests/test_devices.py pass cleanly."
    )
    return "pennylane", prompt


def setup_swe_pennylane_4376(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 4376: PennyLaneAI/pennylane wire allocation in statevector transforms."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "pennylane"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "wires.py").write_text(
        '"""Quantum wire allocation."""\n\n'
        "def allocate_wires(wire_names: list[str], n_qubits: int) -> list[str]:\n"
        "    # BUG: Raises ValueError when len(wire_names) < n_qubits instead of generating aux wires\n"
        "    if len(wire_names) < n_qubits:\n"
        "        raise ValueError('Not enough wires')\n"
        "    return wire_names[:n_qubits]\n"
    )

    (tests / "test_wires.py").write_text(
        "import pytest\nfrom pennylane.wires import allocate_wires\n\n"
        "def test_exact_wires():\n"
        "    assert allocate_wires(['q0', 'q1'], 2) == ['q0', 'q1']\n\n"
        "def test_aux_wire_generation():\n"
        "    assert allocate_wires(['q0'], 3) == ['q0', 'aux_1', 'aux_2']\n"
    )

    prompt = (
        "In `pennylane/wires.py`, modify `allocate_wires` so that if `len(wire_names) < n_qubits`, "
        "it automatically generates auxiliary wire names `[f'aux_{i}' for i in range(1, needed + 1)]` "
        "appended to the wire list. Ensure tests in tests/test_wires.py pass."
    )
    return "pennylane", prompt


def setup_swe_pennylane_4402(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 4402: PennyLaneAI/pennylane preserve gradient tapes across batch evaluations."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "pennylane"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "gradients.py").write_text(
        '"""Gradient tape evaluation."""\n\n'
        "def record_tape(params: list[float]) -> list[float]:\n"
        "    # BUG: In-place clears the caller's parameter list\n"
        "    recorded = list(params)\n"
        "    params.clear()\n"
        "    return recorded\n"
    )

    (tests / "test_gradients.py").write_text(
        "import pytest\nfrom pennylane.gradients import record_tape\n\n"
        "def test_tape_returns_copy():\n"
        "    p = [0.1, 0.2]\n"
        "    tape = record_tape(p)\n"
        "    assert tape == [0.1, 0.2]\n\n"
        "def test_caller_params_preserved():\n"
        "    p = [0.1, 0.2]\n"
        "    record_tape(p)\n"
        "    assert p == [0.1, 0.2]\n"
    )

    prompt = (
        "In `pennylane/gradients.py`, fix `record_tape` so that it returns a copy of `params` "
        "without clearing or mutating the caller's `params` list. Ensure tests in tests/test_gradients.py pass."
    )
    return "pennylane", prompt


def setup_swe_pennylane_4488(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 4488: PennyLaneAI/pennylane correct parameter broadcasting in hybrid circuits."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "pennylane"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "qnode.py").write_text(
        '"""Quantum Node execution."""\n\n'
        "def broadcast_params(params: list) -> list[list[float]]:\n"
        "    # BUG: Fails to wrap 1D single-circuit parameters in a batch dimension\n"
        "    if not params:\n"
        "        return []\n"
        "    return params\n"
    )

    (tests / "test_qnode.py").write_text(
        "import pytest\nfrom pennylane.qnode import broadcast_params\n\n"
        "def test_batched_input():\n"
        "    assert broadcast_params([[1.0], [2.0]]) == [[1.0], [2.0]]\n\n"
        "def test_unbatched_input_wrapped():\n"
        "    assert broadcast_params([1.0, 2.0]) == [[1.0, 2.0]]\n"
    )

    prompt = (
        "In `pennylane/qnode.py`, modify `broadcast_params` so that if `params` is a 1D list (elements are not lists), "
        "it wraps it into `[params]` to ensure 2D batch shape. If already 2D, return unchanged. Ensure tests in tests/test_qnode.py pass."
    )
    return "pennylane", prompt


def setup_swe_pennylane_4512(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 4512: PennyLaneAI/pennylane measurement shape inference for multi-qubit observables."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "pennylane"
    pkg.mkdir(exist_ok=True)
    tests = ws / "tests"
    tests.mkdir(exist_ok=True)

    (pkg / "__init__.py").write_text("")
    (pkg / "measurements.py").write_text(
        '"""Quantum measurement transformations."""\n\n'
        "def infer_measurement_shape(n_shots: int, n_wires: int, m_type: str = 'sample') -> tuple[int, ...]:\n"
        "    # BUG: Returns (n_shots,) instead of (n_shots, n_wires) for multi-qubit sampling\n"
        "    if m_type == 'expval':\n"
        "        return ()\n"
        "    return (n_shots,)\n"
    )

    (tests / "test_measurements.py").write_text(
        "import pytest\nfrom pennylane.measurements import infer_measurement_shape\n\n"
        "def test_expval_scalar():\n"
        "    assert infer_measurement_shape(100, 2, 'expval') == ()\n\n"
        "def test_sample_shape_multiqubit():\n"
        "    assert infer_measurement_shape(100, 3, 'sample') == (100, 3)\n"
    )

    prompt = (
        "In `pennylane/measurements.py`, fix `infer_measurement_shape`: for `m_type == 'sample'`, "
        "return `(n_shots, n_wires)` instead of `(n_shots,)`. Ensure tests in tests/test_measurements.py pass cleanly."
    )
    return "pennylane", prompt


from scripts.tse_60_task_fixtures import EXTENDED_40_TASK_REGISTRY

BASE_20_TASK_REGISTRY = {
    # 5 cmd2 tasks
    "swe_cmd2_744": setup_swe_cmd2_744,
    "swe_cmd2_755": setup_swe_cmd2_755,
    "swe_cmd2_760": setup_swe_cmd2_760,
    "swe_cmd2_770": setup_swe_cmd2_770,
    "swe_cmd2_780": setup_swe_cmd2_780,
    # 5 sympy tasks
    "swe_sympy_19512": setup_swe_sympy_19512,
    "swe_sympy_20967": setup_swe_sympy_20967,
    "swe_sympy_18033": setup_swe_sympy_18033,
    "swe_sympy_18189": setup_swe_sympy_18189,
    "swe_sympy_18621": setup_swe_sympy_18621,
    # 5 pennylane tasks
    "swe_pennylane_5063": setup_swe_pennylane_5063,
    "swe_pennylane_4376": setup_swe_pennylane_4376,
    "swe_pennylane_4402": setup_swe_pennylane_4402,
    "swe_pennylane_4488": setup_swe_pennylane_4488,
    "swe_pennylane_4512": setup_swe_pennylane_4512,
    # 5 repo maintenance tasks
    "repo_env_var_interpolator": setup_task_env_interpolator,
    "repo_json_schema_coercer": setup_task_schema_coercer,
    "repo_csv_schema_validator": setup_task_csv_validator,
    "repo_cli_parser_engine": setup_task_cli_engine,
    "repo_sql_query_builder": setup_task_sql_builder,
}

TASK_REGISTRY = {**BASE_20_TASK_REGISTRY, **EXTENDED_40_TASK_REGISTRY}

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
    resume: bool = False,
    actor_model_name: str = None,
    verifier_model_name: str = None,
) -> dict:
    trial_id = f"{arm}_{task_id}"
    trial_dir = output_root / arm / task_id

    # If resume is requested and summary.json exists, return saved summary
    summary_file = trial_dir / "summary.json"
    if resume and summary_file.exists():
        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
            return saved
        except Exception:
            pass

    if trial_dir.exists():
        shutil.rmtree(trial_dir)
    trial_dir.mkdir(parents=True, exist_ok=True)

    ws_dir = trial_dir / "workspace"
    baseline_dir = trial_dir / "baseline"
    pkg_name, prompt = setup_fn(ws_dir)
    shutil.copytree(ws_dir, baseline_dir)

    cfg_file = ARM_CONFIGS[arm]
    cfg = load_config(cfg_file)
    if actor_model_name:
        cfg.model.name = actor_model_name
    if verifier_model_name and cfg.verifier:
        cfg.verifier.name = verifier_model_name

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
    try:
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
    except Exception as exc:
        print(f'  [ERROR in run_task] {exc}')
        runtime_summary = None
    elapsed = time.monotonic() - start_time
    try:
        store.close()
    except Exception:
        pass

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
        "steps_completed": runtime_summary.get("steps_completed", 0) if runtime_summary else 0,
        "policy_tokens": runtime_summary.get("total_online_tokens", 0) if runtime_summary else 0,
        "verifier_spent": runtime_summary.get("verification_spent", 0.0) if runtime_summary else 0.0,
    }

    summary_file.write_text(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description="Run Action-Time Verification Experiment")
    parser.add_argument("--arms", default="arm0_unverified,arm1_random,arm2_selective", help="Comma-separated arms")
    parser.add_argument("--tasks", type=int, default=len(TASK_REGISTRY), help="Number of tasks to run")
    parser.add_argument("--output", default="artifacts/action_time_study", help="Output directory")
    parser.add_argument("--resume", action="store_true", help="Resume from existing trial summary if already completed")
    parser.add_argument("--actor-model", default=None, help="Override actor model name")
    parser.add_argument("--verifier-model", default=None, help="Override verifier model name")
    args = parser.parse_args()

    out_dir = REPO_ROOT / args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    arms = [a.strip() for a in args.arms.split(",")]
    task_keys = list(TASK_REGISTRY.keys())[:args.tasks]

    print(f"=== Starting IEEE TSE Action-Time Verification Experiment ===")
    print(f"Arms ({len(arms)}): {arms}")
    print(f"Tasks ({len(task_keys)}): {task_keys}")
    print(f"Actor Model Override: {args.actor_model}")
    print(f"Verifier Model Override: {args.verifier_model}")
    print(f"Total Trials to Run: {len(arms) * len(task_keys)}")
    print(f"Output Directory: {out_dir}\n")

    results = []
    completed_count = 0
    total_trials = len(arms) * len(task_keys)

    for task_idx, task_id in enumerate(task_keys, 1):
        setup_fn = TASK_REGISTRY[task_id]
        print(f"\n--- Task {task_idx}/{len(task_keys)}: {task_id} ---")
        for arm in arms:
            completed_count += 1
            print(f"[{completed_count}/{total_trials}] Running [{arm}] on [{task_id}]...")
            res = run_single_arm_task(
                arm,
                task_id,
                setup_fn,
                out_dir,
                resume=args.resume,
                actor_model_name=args.actor_model,
                verifier_model_name=args.verifier_model,
            )
            print(f"  -> Resolved: {res['resolved']} | Verified Decisions: {res['verified_decisions']} | Blocked: {res['blocked_actions']} | Time: {res['elapsed_seconds']}s")
            results.append(res)

    # Master report
    report_file = out_dir / "action_time_report.json"
    report_file.write_text(json.dumps(results, indent=2))

    print("\n=== Experiment Complete ===")
    print(f"Report written to: {report_file}")


if __name__ == "__main__":
    main()
