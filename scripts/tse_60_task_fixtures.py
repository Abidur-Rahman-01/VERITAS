"""
tse_60_task_fixtures.py

Comprehensive 60-task repository repair benchmark cohort for IEEE TSE Action-Time Verification Study:
- Tasks 1-5: SWE-bench cmd2 (Tasks 744, 755, 760, 770, 780)
- Tasks 6-10: SWE-bench sympy (Tasks 19512, 20967, 18033, 18189, 18621)
- Tasks 11-15: SWE-bench pennylane (Tasks 5063, 4376, 4402, 4488, 4512)
- Tasks 16-20: Repo Maintenance (interpolator, coercer, csv_validator, cli_engine, sql_builder)
- Tasks 21-24: Benchmark Core (topological_sorter, url_router, constant_time_compare, iso_duration)
- Tasks 25-34: Coding Calibration (cli_arg_parser, template_formatter, lru_cache, nested_dict,
               url_encoder, markdown_links, header_normalizer, semver, csv_sniffer, retry_backoff)
- Tasks 35-39: Extended cmd2 (prompt_formatter, history_search, alias_resolver, stderr_redirect, transcript_comments)
- Tasks 40-44: Extended sympy (rational_denom, poly_degree, complex_conjugate, upper_tri_det, expr_subst)
- Tasks 45-49: Extended pennylane (pauli_commutator, statevector_norm, diag_expval, gate_decompose, density_trace)
- Tasks 50-60: Production Systems (jwt_parser, cron_matcher, table_formatter, bloom_filter, rate_limiter,
               diff_parser, uuid_validator, graph_cycles, base64_stream, levenshtein_dist, ip_cidr_matcher)
"""

from pathlib import Path
import math
import os
import re

# Extended task fixtures (Tasks 21 to 60)

# Import existing core benchmark fixtures
from scripts.run_model_comparison_benchmark import (
    setup_task_topological_sorter, setup_task_router_matcher,
    setup_task_constant_time_compare, setup_task_iso_duration,
)

# Import existing calibration fixtures
from scripts.run_coding_calibration import (
    setup_task_cli_parser, setup_task_template_formatter, setup_task_lru_cache,
    setup_task_nested_dict, setup_task_url_encoder, setup_task_markdown_links,
    setup_task_header_normalizer, setup_task_semver, setup_task_csv_sniffer,
    setup_task_retry_backoff,
)


# --- Tasks 35-39: Extended cmd2 Tasks ---

def setup_swe_cmd2_790(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 790: cmd2 shell prompt formatting with escape sequences."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "cmd2"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "prompt.py").write_text(
        '"""Prompt formatter."""\n\n'
        "def format_prompt(template: str, user: str = 'guest') -> str:\n"
        "    # BUG: Fails to replace {user} when prompt has escaped braces {{...}}\n"
        "    if '{{' in template:\n"
        "        return template\n"
        "    return template.replace('{user}', user)\n"
    )
    (tests / "test_prompt.py").write_text(
        "from cmd2.prompt import format_prompt\n\n"
        "def test_simple_prompt():\n"
        "    assert format_prompt('{user}> ', 'admin') == 'admin> '\n\n"
        "def test_escaped_braces():\n"
        "    assert format_prompt('{{{user}}}', 'root') == '{root}'\n"
    )
    prompt = "In `cmd2/prompt.py`, fix `format_prompt` to properly replace `{user}` with `user` even if template contains escaped double braces `{{` or `}}`. Ensure tests in tests/test_prompt.py pass."
    return "cmd2", prompt


def setup_swe_cmd2_800(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 800: cmd2 history search reverse regex index."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "cmd2"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "search.py").write_text(
        '"""History reverse search."""\nimport re\n\n'
        "def find_last_matching_command(history: list[str], regex: str) -> str | None:\n"
        "    # BUG: Searches forward instead of backward, returning earliest match instead of last\n"
        "    for cmd in history:\n"
        "        if re.search(regex, cmd):\n"
        "            return cmd\n"
        "    return None\n"
    )
    (tests / "test_search.py").write_text(
        "from cmd2.search import find_last_matching_command\n\n"
        "def test_find_last_match():\n"
        "    h = ['git status', 'ls -l', 'git commit -m first', 'pwd', 'git commit -m second']\n"
        "    assert find_last_matching_command(h, r'git commit') == 'git commit -m second'\n"
    )
    prompt = "In `cmd2/search.py`, fix `find_last_matching_command` to search backward through history and return the most recent matching command. Ensure tests in tests/test_search.py pass."
    return "cmd2", prompt


def setup_swe_cmd2_810(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 810: cmd2 alias multi-hop resolution."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "cmd2"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "aliases.py").write_text(
        '"""Alias manager."""\n\n'
        "def resolve_alias(alias_map: dict[str, str], name: str) -> str:\n"
        "    # BUG: Only does 1-hop lookup instead of following chained aliases\n"
        "    return alias_map.get(name, name)\n"
    )
    (tests / "test_aliases.py").write_text(
        "from cmd2.aliases import resolve_alias\n\n"
        "def test_single_hop():\n"
        "    assert resolve_alias({'g': 'git'}, 'g') == 'git'\n\n"
        "def test_chained_alias():\n"
        "    # Multi-hop: 'g' -> 'git' -> '/usr/bin/git'\n"
        "    assert resolve_alias({'g': 'git', 'git': '/usr/bin/git'}, 'g') == '/usr/bin/git'\n"
    )
    prompt = "In `cmd2/aliases.py`, fix `resolve_alias` to resolve chained multi-hop aliases iteratively until no further alias expansion exists. Ensure tests in tests/test_aliases.py pass."
    return "cmd2", prompt


def setup_swe_cmd2_820(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 820: cmd2 pipe stderr redirection 2>&1."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "cmd2"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "redirect.py").write_text(
        '"""Redirection handler."""\n\n'
        "def parse_redirect(command_line: str) -> dict:\n"
        "    # BUG: Fails to detect '2>&1' and only detects '>'\n"
        "    if '>' in command_line:\n"
        "        cmd, out = command_line.split('>', 1)\n"
        "        return {'command': cmd.strip(), 'stdout': out.strip(), 'combine_stderr': False}\n"
        "    return {'command': command_line.strip(), 'stdout': None, 'combine_stderr': False}\n"
    )
    (tests / "test_redirect.py").write_text(
        "from cmd2.redirect import parse_redirect\n\n"
        "def test_simple_out():\n"
        "    assert parse_redirect('build.sh > out.log')['stdout'] == 'out.log'\n\n"
        "def test_combine_stderr():\n"
        "    res = parse_redirect('build.sh > out.log 2>&1')\n"
        "    assert res['stdout'] == 'out.log'\n"
        "    assert res['combine_stderr'] is True\n"
    )
    prompt = "In `cmd2/redirect.py`, fix `parse_redirect` to detect `'2>&1'` and set `'combine_stderr': True` with stripped stdout file path. Ensure tests in tests/test_redirect.py pass."
    return "cmd2", prompt


def setup_swe_cmd2_830(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 830: cmd2 transcript comment line stripping."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "cmd2"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "comments.py").write_text(
        '"""Comment filter."""\n\n'
        "def strip_comments(lines: list[str]) -> list[str]:\n"
        "    # BUG: Strips lines containing '#' anywhere, even inside strings\n"
        "    return [l for l in lines if '#' not in l]\n"
    )
    (tests / "test_comments.py").write_text(
        "from cmd2.comments import strip_comments\n\n"
        "def test_strip_full_line_comment():\n"
        "    assert strip_comments(['# comment', 'run']) == ['run']\n\n"
        "def test_preserve_inline_hash_in_quotes():\n"
        "    assert strip_comments(['echo \"#tag\"']) == ['echo \"#tag\"']\n"
    )
    prompt = "In `cmd2/comments.py`, fix `strip_comments` to only drop lines that start with '#' (ignoring leading whitespace), preserving lines with inline hashes. Ensure tests in tests/test_comments.py pass."
    return "cmd2", prompt


# --- Tasks 40-44: Extended sympy Tasks ---

def setup_swe_sympy_18800(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 18800: sympy negative denominator normalization in rational fractions."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "sympy"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "rational.py").write_text(
        '"""Rational number representations."""\nimport math\n\n'
        "def make_rational(num: int, den: int) -> tuple[int, int]:\n"
        "    if den == 0:\n"
        "        raise ZeroDivisionError('Denominator cannot be zero')\n"
        "    g = math.gcd(abs(num), abs(den))\n"
        "    # BUG: Leaves negative sign on denominator instead of normalizing to numerator\n"
        "    return (num // g, den // g)\n"
    )
    (tests / "test_rational.py").write_text(
        "from sympy.rational import make_rational\n\n"
        "def test_positive_denom():\n"
        "    assert make_rational(4, 6) == (2, 3)\n\n"
        "def test_negative_denom():\n"
        "    assert make_rational(1, -2) == (-1, 2)\n"
        "    assert make_rational(-1, -2) == (1, 2)\n"
    )
    prompt = "In `sympy/rational.py`, fix `make_rational`: if `den < 0`, negate both `num` and `den` so denominator is always positive. Ensure tests in tests/test_rational.py pass."
    return "sympy", prompt


def setup_swe_sympy_18900(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 18900: sympy polynomial degree calculation for multivariate monomials."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "sympy"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "monomial.py").write_text(
        '"""Monomial operations."""\n\n'
        "def total_degree(powers: dict[str, int]) -> int:\n"
        "    # BUG: Returns max power instead of sum of powers\n"
        "    if not powers:\n"
        "        return 0\n"
        "    return max(powers.values())\n"
    )
    (tests / "test_monomial.py").write_text(
        "from sympy.monomial import total_degree\n\n"
        "def test_single_var():\n"
        "    assert total_degree({'x': 3}) == 3\n\n"
        "def test_multivariate_sum():\n"
        "    # x^2 * y^3 * z^1 -> total degree 6\n"
        "    assert total_degree({'x': 2, 'y': 3, 'z': 1}) == 6\n"
    )
    prompt = "In `sympy/monomial.py`, fix `total_degree` to return the sum of all variable exponents (`sum(powers.values())`). Ensure tests in tests/test_monomial.py pass."
    return "sympy", prompt


def setup_swe_sympy_19000(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 19000: sympy complex conjugate of rational expressions."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "sympy"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "complex_tools.py").write_text(
        '"""Complex numbers."""\n\n'
        "def conjugate(re: float, im: float) -> tuple[float, float]:\n"
        "    # BUG: Inverts real part instead of imaginary part\n"
        "    return (-re, im)\n"
    )
    (tests / "test_complex.py").write_text(
        "from sympy.complex_tools import conjugate\n\n"
        "def test_conjugate():\n"
        "    assert conjugate(3.0, 4.0) == (3.0, -4.0)\n"
        "    assert conjugate(2.0, -5.0) == (2.0, 5.0)\n"
    )
    prompt = "In `sympy/complex_tools.py`, fix `conjugate` so that it returns `(re, -im)`. Ensure tests in tests/test_complex.py pass."
    return "sympy", prompt


def setup_swe_sympy_19100(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 19100: sympy 3x3 upper triangular matrix determinant."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "sympy"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "tri_det.py").write_text(
        '"""Triangular matrix determinant."""\n\n'
        "def triangular_det_3x3(mat: list[list[float]]) -> float:\n"
        "    # BUG: Adds diagonal elements instead of multiplying them\n"
        "    return mat[0][0] + mat[1][1] + mat[2][2]\n"
    )
    (tests / "test_tri_det.py").write_text(
        "from sympy.tri_det import triangular_det_3x3\n\n"
        "def test_det():\n"
        "    m = [[2.0, 5.0, 7.0],\n"
        "         [0.0, 3.0, 4.0],\n"
        "         [0.0, 0.0, 4.0]]\n"
        "    assert triangular_det_3x3(m) == 24.0\n"
    )
    prompt = "In `sympy/tri_det.py`, fix `triangular_det_3x3` to compute the product of diagonal elements `mat[0][0] * mat[1][1] * mat[2][2]`. Ensure tests in tests/test_tri_det.py pass."
    return "sympy", prompt


def setup_swe_sympy_19200(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 19200: sympy symbolic expression substitution immutability."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "sympy"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "subst.py").write_text(
        '"""Expression substitution."""\n\n'
        "def substitute(expr: dict, replacements: dict) -> dict:\n"
        "    # BUG: Mutates expr in place instead of returning a new dict\n"
        "    for k, v in replacements.items():\n"
        "        if k in expr:\n"
        "            expr[k] = v\n"
        "    return expr\n"
    )
    (tests / "test_subst.py").write_text(
        "from sympy.subst import substitute\n\n"
        "def test_immutability():\n"
        "    orig = {'x': 1, 'y': 2}\n"
        "    res = substitute(orig, {'x': 10})\n"
        "    assert res == {'x': 10, 'y': 2}\n"
        "    assert orig == {'x': 1, 'y': 2}\n"
    )
    prompt = "In `sympy/subst.py`, fix `substitute` to copy `expr` before replacing variables so original dict is never modified. Ensure tests in tests/test_subst.py pass."
    return "sympy", prompt


# --- Tasks 45-49: Extended pennylane Tasks ---

def setup_swe_pennylane_5100(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 5100: pennylane Pauli commutator lookup."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "pennylane"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "pauli.py").write_text(
        '"""Pauli commutator arithmetic."""\n\n'
        "def pauli_commutator(p1: str, p2: str) -> str:\n"
        "    # BUG: Commutator of identical operators should be '0', but returns operator itself\n"
        "    if p1 == p2:\n"
        "        return p1\n"
        "    if (p1, p2) == ('X', 'Y'): return '2iZ'\n"
        "    if (p1, p2) == ('Y', 'X'): return '-2iZ'\n"
        "    return '0'\n"
    )
    (tests / "test_pauli.py").write_text(
        "from pennylane.pauli import pauli_commutator\n\n"
        "def test_identical_operators():\n"
        "    assert pauli_commutator('X', 'X') == '0'\n"
        "    assert pauli_commutator('Z', 'Z') == '0'\n\n"
        "def test_xy():\n"
        "    assert pauli_commutator('X', 'Y') == '2iZ'\n"
    )
    prompt = "In `pennylane/pauli.py`, fix `pauli_commutator` so that when `p1 == p2`, it returns `'0'`. Ensure tests in tests/test_pauli.py pass."
    return "pennylane", prompt


def setup_swe_pennylane_5200(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 5200: pennylane quantum statevector normalization."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "pennylane"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "state.py").write_text(
        '"""Quantum state utilities."""\nimport math\n\n'
        "def normalize_state(vec: list[float]) -> list[float]:\n"
        "    # BUG: Divides by sum of amplitudes instead of Euclidean L2 norm sqrt(sum(x^2))\n"
        "    s = sum(vec)\n"
        "    if s == 0:\n"
        "        return vec\n"
        "    return [x / s for x in vec]\n"
    )
    (tests / "test_state.py").write_text(
        "import math\nfrom pennylane.state import normalize_state\n\n"
        "def test_l2_norm():\n"
        "    vec = [3.0, 4.0]\n"
        "    res = normalize_state(vec)\n"
        "    assert math.isclose(res[0], 0.6)\n"
        "    assert math.isclose(res[1], 0.8)\n"
    )
    prompt = "In `pennylane/state.py`, fix `normalize_state` to normalize by L2 Euclidean norm `math.sqrt(sum(x*x for x in vec))`. Ensure tests in tests/test_state.py pass."
    return "pennylane", prompt


def setup_swe_pennylane_5300(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 5300: pennylane expectation value for diagonal observable."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "pennylane"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "expval.py").write_text(
        '"""Expectation value calculation."""\n\n'
        "def compute_diag_expval(diag: list[float], probs: list[float]) -> float:\n"
        "    # BUG: Multiplies probability by index instead of eigenvalue\n"
        "    return sum(i * p for i, p in enumerate(probs))\n"
    )
    (tests / "test_expval.py").write_text(
        "from pennylane.expval import compute_diag_expval\n\n"
        "def test_diag_expval():\n"
        "    # Eigenvalues: [1.0, -1.0], Probs: [0.7, 0.3] -> 1*0.7 + (-1)*0.3 = 0.4\n"
        "    assert round(compute_diag_expval([1.0, -1.0], [0.7, 0.3]), 2) == 0.4\n"
    )
    prompt = "In `pennylane/expval.py`, fix `compute_diag_expval` to compute `sum(d * p for d, p in zip(diag, probs))`. Ensure tests in tests/test_expval.py pass."
    return "pennylane", prompt


def setup_swe_pennylane_5400(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 5400: pennylane gate decomposition count."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "pennylane"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "decomp.py").write_text(
        '"""Gate decomposition."""\n\n'
        "def decompose_gate(gate_name: str) -> list[str]:\n"
        "    # BUG: Returns empty list for Swap gate instead of 3 CNOT gates\n"
        "    if gate_name == 'SWAP':\n"
        "        return []\n"
        "    return [gate_name]\n"
    )
    (tests / "test_decomp.py").write_text(
        "from pennylane.decomp import decompose_gate\n\n"
        "def test_swap_decomp():\n"
        "    assert decompose_gate('SWAP') == ['CNOT', 'CNOT', 'CNOT']\n\n"
        "def test_single():\n"
        "    assert decompose_gate('H') == ['H']\n"
    )
    prompt = "In `pennylane/decomp.py`, fix `decompose_gate`: for `'SWAP'`, return `['CNOT', 'CNOT', 'CNOT']`. Ensure tests in tests/test_decomp.py pass."
    return "pennylane", prompt


def setup_swe_pennylane_5500(ws: Path) -> tuple[str, str]:
    """SWE-bench Task 5500: pennylane density matrix trace verification."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "pennylane"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "density.py").write_text(
        '"""Density matrix utilities."""\nimport math\n\n'
        "def is_valid_density_trace(mat: list[list[float]], tol: float = 1e-6) -> bool:\n"
        "    # BUG: Checks trace == 0.0 instead of trace == 1.0\n"
        "    tr = sum(mat[i][i] for i in range(len(mat)))\n"
        "    return math.isclose(tr, 0.0, abs_tol=tol)\n"
    )
    (tests / "test_density.py").write_text(
        "from pennylane.density import is_valid_density_trace\n\n"
        "def test_valid_trace():\n"
        "    mat = [[0.5, 0.0], [0.0, 0.5]]\n"
        "    assert is_valid_density_trace(mat) is True\n\n"
        "def test_invalid_trace():\n"
        "    mat = [[0.2, 0.0], [0.0, 0.2]]\n"
        "    assert is_valid_density_trace(mat) is False\n"
    )
    prompt = "In `pennylane/density.py`, fix `is_valid_density_trace` so that it verifies `math.isclose(tr, 1.0, abs_tol=tol)`. Ensure tests in tests/test_density.py pass."
    return "pennylane", prompt


# --- Tasks 50-60: Production Systems & Data Utilities ---

def setup_repo_jwt_token_parser(ws: Path) -> tuple[str, str]:
    """Task 50: JWT base64url header/payload decoding."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "jwtsimple"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "jwt.py").write_text(
        '"""JWT parser."""\nimport base64, json\n\n'
        "def parse_jwt_payload(token: str) -> dict:\n"
        "    parts = token.split('.')\n"
        "    # BUG: Fails on missing base64 padding without adding '=' to length multiple of 4\n"
        "    payload_b64 = parts[1]\n"
        "    decoded = base64.urlsafe_b64decode(payload_b64)\n"
        "    return json.loads(decoded)\n"
    )
    (tests / "test_jwt.py").write_text(
        "import base64, json\nfrom jwtsimple.jwt import parse_jwt_payload\n\n"
        "def test_unpadded_payload():\n"
        "    # JSON: {'sub': '123'}\n"
        "    token = 'header.eyJzdWIiOiIxMjMifQ.sig'\n"
        "    assert parse_jwt_payload(token) == {'sub': '123'}\n"
    )
    prompt = "In `jwtsimple/jwt.py`, fix `parse_jwt_payload` to add `'=' * (-len(payload_b64) % 4)` before decoding so unpadded base64 strings decode cleanly. Ensure tests in tests/test_jwt.py pass."
    return "jwtsimple", prompt


def setup_repo_cron_expression_matcher(ws: Path) -> tuple[str, str]:
    """Task 51: 5-field cron minute schedule matcher."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "cronkit"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "cron.py").write_text(
        '"""Cron matcher."""\n\n'
        "def matches_minute(field: str, current_minute: int) -> bool:\n"
        "    # BUG: Fails on step expressions like '*/15'\n"
        "    if field == '*':\n"
        "        return True\n"
        "    return field == str(current_minute)\n"
    )
    (tests / "test_cron.py").write_text(
        "from cronkit.cron import matches_minute\n\n"
        "def test_star():\n"
        "    assert matches_minute('*', 14) is True\n\n"
        "def test_step():\n"
        "    assert matches_minute('*/15', 30) is True\n"
        "    assert matches_minute('*/15', 31) is False\n"
    )
    prompt = "In `cronkit/cron.py`, fix `matches_minute`: if field starts with `'*/'`, parse step integer `s` and return `current_minute % s == 0`. Ensure tests in tests/test_cron.py pass."
    return "cronkit", prompt


def setup_repo_markdown_table_formatter(ws: Path) -> tuple[str, str]:
    """Task 52: Markdown table column alignment."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "mdtable"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "table.py").write_text(
        '"""Markdown table formatter."""\n\n'
        "def format_row(cells: list[str]) -> str:\n"
        "    # BUG: Does not enclose row in '| ' and ' |'\n"
        "    return ' | '.join(cells)\n"
    )
    (tests / "test_table.py").write_text(
        "from mdtable.table import format_row\n\n"
        "def test_row():\n"
        "    assert format_row(['A', 'B']) == '| A | B |'\n"
    )
    prompt = "In `mdtable/table.py`, fix `format_row` so that it returns `f'| {\" | \".join(cells)} |'`. Ensure tests in tests/test_table.py pass."
    return "mdtable", prompt


def setup_repo_bloom_filter(ws: Path) -> tuple[str, str]:
    """Task 53: Bloom filter bit array calculation."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "bloom"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "filter.py").write_text(
        '"""Bloom filter."""\n\n'
        "class BloomFilter:\n"
        "    def __init__(self, size: int = 16):\n"
        "        self.size = size\n"
        "        self.bits = [0] * size\n\n"
        "    def add(self, item: str):\n"
        "        # BUG: Only sets one bit instead of two salt hashes (hash(item) and hash(item + 'salt'))\n"
        "        idx = hash(item) % self.size\n"
        "        self.bits[idx] = 1\n\n"
        "    def contains(self, item: str) -> bool:\n"
        "        idx = hash(item) % self.size\n"
        "        return self.bits[idx] == 1\n"
    )
    (tests / "test_bloom.py").write_text(
        "from bloom.filter import BloomFilter\n\n"
        "def test_two_hash_bits():\n"
        "    bf = BloomFilter(64)\n"
        "    bf.add('hello')\n"
        "    assert sum(bf.bits) == 2\n"
    )
    prompt = "In `bloom/filter.py`, ensure `BloomFilter` hashes with two indices `(hash(item) % self.size)` and `(hash(item + '_salt') % self.size)` in both `add` and `contains`. Ensure tests in tests/test_bloom.py pass."
    return "bloom", prompt


def setup_repo_rate_limiter_token_bucket(ws: Path) -> tuple[str, str]:
    """Task 54: Token bucket rate limiter."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "ratelimit"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "bucket.py").write_text(
        '"""Token bucket."""\n\n'
        "class TokenBucket:\n"
        "    def __init__(self, capacity: int, fill_rate: float):\n"
        "        self.capacity = capacity\n"
        "        self.fill_rate = fill_rate\n"
        "        self.tokens = capacity\n\n"
        "    def consume(self, amount: int = 1) -> bool:\n"
        "        # BUG: Consumes even when tokens < amount\n"
        "        self.tokens -= amount\n"
        "        return True\n"
    )
    (tests / "test_bucket.py").write_text(
        "from ratelimit.bucket import TokenBucket\n\n"
        "def test_consume():\n"
        "    b = TokenBucket(2, 1.0)\n"
        "    assert b.consume(1) is True\n"
        "    assert b.consume(1) is True\n"
        "    assert b.consume(1) is False\n"
    )
    prompt = "In `ratelimit/bucket.py`, fix `consume`: if `self.tokens >= amount`, decrement tokens and return `True`, else return `False`. Ensure tests in tests/test_bucket.py pass."
    return "ratelimit", prompt


def setup_repo_diff_patch_parser(ws: Path) -> tuple[str, str]:
    """Task 55: Unified diff chunk header parser."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "patcher"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "diff.py").write_text(
        '"""Unified diff header parser."""\nimport re\n\n'
        "def parse_hunk_header(line: str) -> tuple[int, int]:\n"
        "    # BUG: Fails when hunk count is omitted, e.g. @@ -1 +1 @@ (implies count=1)\n"
        "    m = re.match(r'@@ -(\\d+),(\\d+) \\+(\\d+),(\\d+) @@', line)\n"
        "    return int(m.group(1)), int(m.group(3))\n"
    )
    (tests / "test_diff.py").write_text(
        "from patcher.diff import parse_hunk_header\n\n"
        "def test_full_header():\n"
        "    assert parse_hunk_header('@@ -10,5 +20,6 @@') == (10, 20)\n\n"
        "def test_single_line_header():\n"
        "    assert parse_hunk_header('@@ -1 +1 @@') == (1, 1)\n"
    )
    prompt = "In `patcher/diff.py`, fix `parse_hunk_header` using regex `r'@@ -(\\d+)(?:,\\d+)? \\+(\\d+)(?:,\\d+)? @@'` to support omitted line counts. Ensure tests in tests/test_diff.py pass."
    return "patcher", prompt


def setup_repo_uuid_validator(ws: Path) -> tuple[str, str]:
    """Task 56: UUID v4 format validator."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "idtools"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "uuid.py").write_text(
        '"""UUID validator."""\nimport re\n\n'
        "def is_valid_uuid4(val: str) -> bool:\n"
        "    # BUG: Allows arbitrary versions instead of enforcing version 4 (8-4-4-4-12 hex with '4' at pos 14)\n"
        "    pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'\n"
        "    return bool(re.match(pattern, val.lower()))\n"
    )
    (tests / "test_uuid.py").write_text(
        "from idtools.uuid import is_valid_uuid4\n\n"
        "def test_valid_v4():\n"
        "    assert is_valid_uuid4('c9a646d3-9c61-4cc9-bc94-e200c8f5f4e1') is True\n\n"
        "def test_invalid_version():\n"
        "    # Version 1 instead of 4\n"
        "    assert is_valid_uuid4('c9a646d3-9c61-1cc9-bc94-e200c8f5f4e1') is False\n"
    )
    prompt = "In `idtools/uuid.py`, fix `is_valid_uuid4` to verify the 3rd group starts with '4': `r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'`. Ensure tests in tests/test_uuid.py pass."
    return "idtools", prompt


def setup_repo_graph_cycle_detector(ws: Path) -> tuple[str, str]:
    """Task 57: Directed graph cycle detector."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "graphs"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "cycle.py").write_text(
        '"""Directed graph cycle detection."""\n\n'
        "def has_cycle(adj: dict[str, list[str]]) -> bool:\n"
        "    # BUG: Returns False unconditionally\n"
        "    return False\n"
    )
    (tests / "test_cycle.py").write_text(
        "from graphs.cycle import has_cycle\n\n"
        "def test_dag():\n"
        "    assert has_cycle({'a': ['b'], 'b': []}) is False\n\n"
        "def test_cycle():\n"
        "    assert has_cycle({'a': ['b'], 'b': ['a']}) is True\n"
    )
    prompt = "In `graphs/cycle.py`, implement `has_cycle` using standard DFS recursion with visiting set to detect directed cycles. Ensure tests in tests/test_cycle.py pass."
    return "graphs", prompt


def setup_repo_base64_stream_codec(ws: Path) -> tuple[str, str]:
    """Task 58: Chunked stream base64 encoder."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "codec"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "stream.py").write_text(
        '"""Stream base64 codec."""\nimport base64\n\n'
        "def encode_chunks(chunks: list[bytes]) -> str:\n"
        "    # BUG: Encodes each chunk separately producing broken concatenated padding\n"
        "    return ''.join(base64.b64encode(c).decode() for c in chunks)\n"
    )
    (tests / "test_stream.py").write_text(
        "import base64\nfrom codec.stream import encode_chunks\n\n"
        "def test_stream_matches_full():\n"
        "    raw = b'hello world from python'\n"
        "    chunks = [raw[:5], raw[5:]]\n"
        "    assert encode_chunks(chunks) == base64.b64encode(raw).decode()\n"
    )
    prompt = "In `codec/stream.py`, fix `encode_chunks` by concatenating all chunks `b''.join(chunks)` before calling `base64.b64encode`. Ensure tests in tests/test_stream.py pass."
    return "codec", prompt


def setup_repo_levenshtein_distance(ws: Path) -> tuple[str, str]:
    """Task 59: Levenshtein edit distance."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "textmetric"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "levenshtein.py").write_text(
        '"""Levenshtein distance."""\n\n'
        "def levenshtein(s1: str, s2: str) -> int:\n"
        "    # BUG: Returns difference in string lengths instead of edit distance\n"
        "    return abs(len(s1) - len(s2))\n"
    )
    (tests / "test_lev.py").write_text(
        "from textmetric.levenshtein import levenshtein\n\n"
        "def test_identical():\n"
        "    assert levenshtein('cat', 'cat') == 0\n\n"
        "def test_single_substitution():\n"
        "    assert levenshtein('cat', 'bat') == 1\n"
    )
    prompt = "In `textmetric/levenshtein.py`, implement `levenshtein` dynamic programming edit distance. Ensure tests in tests/test_lev.py pass."
    return "textmetric", prompt


def setup_repo_ip_subnet_matcher(ws: Path) -> tuple[str, str]:
    """Task 60: IPv4 CIDR subnet containment checker."""
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "netaddr"; pkg.mkdir(exist_ok=True)
    tests = ws / "tests"; tests.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "cidr.py").write_text(
        '"""CIDR subnet checker."""\nimport ipaddress\n\n'
        "def is_ip_in_network(ip_str: str, cidr_str: str) -> bool:\n"
        "    # BUG: Inverted boolean logic\n"
        "    net = ipaddress.ip_network(cidr_str, strict=False)\n"
        "    ip = ipaddress.ip_address(ip_str)\n"
        "    return ip not in net\n"
    )
    (tests / "test_cidr.py").write_text(
        "from netaddr.cidr import is_ip_in_network\n\n"
        "def test_inside_subnet():\n"
        "    assert is_ip_in_network('192.168.1.5', '192.168.1.0/24') is True\n\n"
        "def test_outside_subnet():\n"
        "    assert is_ip_in_network('10.0.0.1', '192.168.1.0/24') is False\n"
    )
    prompt = "In `netaddr/cidr.py`, fix `is_ip_in_network` so that it returns `ip in net`. Ensure tests in tests/test_cidr.py pass."
    return "netaddr", prompt


# Registry containing tasks 21 to 60
EXTENDED_40_TASK_REGISTRY = {
    # 21-24: benchmark core
    "repo_topological_sorter": setup_task_topological_sorter,
    "repo_url_router": setup_task_router_matcher,
    "repo_constant_time_compare": setup_task_constant_time_compare,
    "repo_iso_duration": setup_task_iso_duration,
    # 25-34: coding calibration
    "repo_cli_arg_parser": setup_task_cli_parser,
    "repo_template_formatter": setup_task_template_formatter,
    "repo_lru_cache": setup_task_lru_cache,
    "repo_nested_dict_resolver": setup_task_nested_dict,
    "repo_url_query_encoder": setup_task_url_encoder,
    "repo_markdown_link_extractor": setup_task_markdown_links,
    "repo_http_header_normalizer": setup_task_header_normalizer,
    "repo_semver_comparator": setup_task_semver,
    "repo_csv_delimiter_detector": setup_task_csv_sniffer,
    "repo_retry_backoff_calculator": setup_task_retry_backoff,
    # 35-39: extended cmd2
    "swe_cmd2_790": setup_swe_cmd2_790,
    "swe_cmd2_800": setup_swe_cmd2_800,
    "swe_cmd2_810": setup_swe_cmd2_810,
    "swe_cmd2_820": setup_swe_cmd2_820,
    "swe_cmd2_830": setup_swe_cmd2_830,
    # 40-44: extended sympy
    "swe_sympy_18800": setup_swe_sympy_18800,
    "swe_sympy_18900": setup_swe_sympy_18900,
    "swe_sympy_19000": setup_swe_sympy_19000,
    "swe_sympy_19100": setup_swe_sympy_19100,
    "swe_sympy_19200": setup_swe_sympy_19200,
    # 45-49: extended pennylane
    "swe_pennylane_5100": setup_swe_pennylane_5100,
    "swe_pennylane_5200": setup_swe_pennylane_5200,
    "swe_pennylane_5300": setup_swe_pennylane_5300,
    "swe_pennylane_5400": setup_swe_pennylane_5400,
    "swe_pennylane_5500": setup_swe_pennylane_5500,
    # 50-60: production systems
    "repo_jwt_token_parser": setup_repo_jwt_token_parser,
    "repo_cron_expression_matcher": setup_repo_cron_expression_matcher,
    "repo_markdown_table_formatter": setup_repo_markdown_table_formatter,
    "repo_bloom_filter": setup_repo_bloom_filter,
    "repo_rate_limiter_token_bucket": setup_repo_rate_limiter_token_bucket,
    "repo_diff_patch_parser": setup_repo_diff_patch_parser,
    "repo_uuid_validator": setup_repo_uuid_validator,
    "repo_graph_cycle_detector": setup_repo_graph_cycle_detector,
    "repo_base64_stream_codec": setup_repo_base64_stream_codec,
    "repo_levenshtein_distance": setup_repo_levenshtein_distance,
    "repo_ip_subnet_matcher": setup_repo_ip_subnet_matcher,
}
