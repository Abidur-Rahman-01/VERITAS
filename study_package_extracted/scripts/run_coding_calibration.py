"""Comprehensive Coding Agent Calibration & Diagnostic Harness.

Implements the multi-stage outcome ladder and failure taxonomy:
- Tier 1: valid_action (Action parsed and executed without contract violation)
- Tier 2: file_edited (Existing repository source files modified)
- Tier 3: applicable_patch (Valid non-empty git patch produced)
- Tier 4: tests_passed (Local test runner passes)
- Tier 5: grader_resolved (Independent ground truth verification passed)

Failure Taxonomy:
- INVALID_OUTPUT: Malformed JSON or unparseable tool call
- NO_EDITS: Agent surrendered or took no file-modifying actions
- WRONG_FILE: Agent edited tests or created standalone scripts rather than target modules
- PATCH_APPLY_ERROR: Git diff application error or syntax invalidation
- TEST_FAILURE: Patch applied to source, but unit tests failed
- INFRASTRUCTURE_ERROR: Sandbox timeout or unexpected crash
"""

import json
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
from veritas.io import digest, file_hash, write_json, write_text
from veritas.models import LocalModel, proposal_from_text
from veritas.runtime import AgentSession, run_phase
from veritas.sandbox import LocalSandbox, make_patch
from veritas.schema import Proposal, Task, Usage
from veritas.state import tree_hash
from veritas.store import EventStore


# -----------------------------------------------------------------------------
# Calibration Task Repository Generator (10 Diverse Held-out SWE Tasks)
# -----------------------------------------------------------------------------

def setup_task_cli_parser(ws: Path):
    """Task 1: CLI Argument Parser with default fallback bug."""
    pkg = ws / "clitools"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .parser import ArgumentParser\n', encoding="utf-8")
    
    code = '''"""CLI Argument Parser."""
class ArgumentParser:
    def __init__(self):
        self.definitions = {}

    def add_argument(self, name: str, default=None, required: bool = False):
        self.definitions[name] = {"default": default, "required": required}

    def parse(self, args: list) -> dict:
        result = {}
        for i in range(len(args)):
            if args[i].startswith("--"):
                key = args[i][2:]
                val = args[i+1] if i + 1 < len(args) and not args[i+1].startswith("--") else True
                result[key] = val
        # Check defaults and required
        for name, spec in self.definitions.items():
            if name not in result:
                # BUG: Inverted logic crashes with KeyError on missing optional arguments
                if not spec["required"]:
                    raise KeyError(f"Optional argument has no assigned value: {name}")
                raise ValueError(f"Missing required argument: {name}")
        return result
'''
    (pkg / "parser.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''from clitools.parser import ArgumentParser

def test_parse_defaults():
    p = ArgumentParser()
    p.add_argument("port", default=8080, required=False)
    p.add_argument("host", default="localhost", required=False)
    res = p.parse(["--port", "9000"])
    assert res["port"] == "9000"
    assert res["host"] == "localhost"

def test_parse_missing_required():
    p = ArgumentParser()
    p.add_argument("config", required=True)
    try:
        p.parse([])
        assert False, "Should raise ValueError"
    except ValueError:
        pass
'''
    (tests / "test_parser.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `clitools/parser.py`, fix `ArgumentParser.parse`: for missing arguments, if `required=False`, "
        "set `result[name] = spec['default']`, and if `required=True`, raise `ValueError(f'Missing required argument: {name}')`. "
        "Inspect the file with read_file, edit it in place with edit_file, run tests with run_tests, and submit final_answer."
    )
    return "clitools", prompt


def setup_task_template_formatter(ws: Path):
    """Task 2: Template String Variable Replacement."""
    pkg = ws / "templating"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .engine import render_template\n', encoding="utf-8")

    code = '''"""Template Engine."""
import re

def render_template(template: str, context: dict) -> str:
    # BUG: Direct dictionary indexing raises KeyError on missing keys instead of returning empty string
    def replacer(match):
        key = match.group(1).strip()
        return str(context[key])
    return re.sub(r"\\{\\{\\s*(\\w+)\\s*\\}\\}", replacer, template)
'''
    (pkg / "engine.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''from templating.engine import render_template

def test_simple_render():
    assert render_template("Hello {{ name }}!", {"name": "Alice"}) == "Hello Alice!"

def test_render_with_special_chars():
    # Value contains regex backslashes and symbols
    assert render_template("Path: {{ path }}", {"path": r"C:\\Users\\admin\\file.txt"}) == r"Path: C:\\Users\\admin\\file.txt"

def test_missing_key():
    assert render_template("Key: {{ missing }}", {}) == "Key: "
'''
    (tests / "test_engine.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `templating/engine.py`, fix `render_template`: when a template key is not present in `context`, "
        "it should default to empty string `\"\"` instead of raising KeyError. "
        "Read `templating/engine.py`, edit it in place using edit_file, run tests with run_tests, and submit final_answer."
    )
    return "templating", prompt


def setup_task_lru_cache(ws: Path):
    """Task 3: LRU Cache Eviction."""
    pkg = ws / "cachelib"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .lru import LRUCache\n', encoding="utf-8")

    code = '''"""LRU Cache."""
from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = OrderedDict()

    def get(self, key):
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key, value):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        # BUG: popitem(last=True) removes the MOST recently added item instead of the LEAST recently used
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=True)
'''
    (pkg / "lru.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''from cachelib.lru import LRUCache

def test_lru_eviction():
    c = LRUCache(2)
    c.put(1, "one")
    c.put(2, "two")
    assert c.get(1) == "one" # access 1, making 2 the oldest
    c.put(3, "three")        # should evict 2
    assert c.get(2) is None
    assert c.get(1) == "one"
    assert c.get(3) == "three"
'''
    (tests / "test_lru.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `cachelib/lru.py`, fix `LRUCache.put`: when the cache exceeds capacity, it must evict the "
        "LEAST recently used item (the oldest entry in OrderedDict), not the newest item. "
        "Read the file, fix the bug with edit_file, test, and submit final_answer."
    )
    return "cachelib", prompt


def setup_task_nested_dict(ws: Path):
    """Task 4: Nested Dictionary Path Resolution."""
    pkg = ws / "configutils"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .resolver import get_nested_path\n', encoding="utf-8")

    code = '''"""Nested Path Resolver."""

def get_nested_path(data: dict, path: str, default=None):
    # BUG: Fails when an intermediate value is None or not a dict instead of returning default
    current = data
    parts = path.split(".")
    for part in parts:
        if part in current:
            current = current[part]
        else:
            return default
    return current
'''
    (pkg / "resolver.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''from configutils.resolver import get_nested_path

def test_valid_path():
    data = {"database": {"host": "localhost", "port": 5432}}
    assert get_nested_path(data, "database.host") == "localhost"

def test_intermediate_none():
    data = {"database": None}
    assert get_nested_path(data, "database.host", default="unknown") == "unknown"

def test_intermediate_non_dict():
    data = {"database": "sqlite:///:memory:"}
    assert get_nested_path(data, "database.host", default="unknown") == "unknown"
'''
    (tests / "test_resolver.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `configutils/resolver.py`, fix `get_nested_path`: traverse the dot-separated path through data. "
        "If an intermediate key does not exist, or its value is None or not a dict when more keys remain, return `default`. "
        "When at the leaf key, return its value if found, else `default`. "
        "Read the file, edit with edit_file, test with run_tests, and submit final_answer."
    )
    return "configutils", prompt


def setup_task_url_encoder(ws: Path):
    """Task 5: URL Multi-Value Query Parameter Encoder."""
    pkg = ws / "webtools"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .query import encode_query_params\n', encoding="utf-8")

    code = '''"""Query Parameter Encoder."""
import urllib.parse

def encode_query_params(params: dict) -> str:
    pairs = []
    for k, v in params.items():
        # BUG: Converts list directly to string representation instead of expanding into multiple key-value pairs
        pairs.append((k, str(v)))
    return "&".join(f"{urllib.parse.quote_plus(str(k))}={urllib.parse.quote_plus(str(v))}" for k, v in pairs)
'''
    (pkg / "query.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''from webtools.query import encode_query_params

def test_simple_params():
    assert encode_query_params({"search": "hello world", "page": 1}) == "search=hello+world&page=1"

def test_list_params():
    res = encode_query_params({"tag": ["python", "ai"], "sort": "date"})
    assert res == "tag=python&tag=ai&sort=date"

def test_empty_params():
    assert encode_query_params({}) == ""
'''
    (tests / "test_query.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `webtools/query.py`, fix `encode_query_params`: if params is empty return empty string \"\". "
        "For each key and value, if the value is a list or tuple, output multiple key=value pairs for each item in the list/tuple. "
        "Ensure keys and values are URL-encoded with urllib.parse.quote_plus. "
        "Inspect the file, edit in place, verify with run_tests, and submit final_answer."
    )
    return "webtools", prompt


def setup_task_markdown_links(ws: Path):
    """Task 6: Markdown Link Extractor (exclude images)."""
    pkg = ws / "mdtools"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .links import extract_links\n', encoding="utf-8")

    code = '''"""Markdown Link Extractor."""
import re

def extract_links(text: str) -> list:
    # BUG: Matches image tags ![alt](url) as regular links because it does not check for preceding '!'
    pattern = r"\\[([^\\]]+)\\]\\(([^\\)]+)\\)"
    return [(m.group(1), m.group(2)) for m in re.finditer(pattern, text)]
'''
    (pkg / "links.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''from mdtools.links import extract_links

def test_extract_simple_link():
    text = "Check out [Google](https://google.com) for searching."
    assert extract_links(text) == [("Google", "https://google.com")]

def test_ignore_image_tags():
    text = "Here is an image ![logo](https://example.com/logo.png) and a link [docs](https://docs.org)."
    assert extract_links(text) == [("docs", "https://docs.org")]

def test_multiple_links():
    text = "[one](http://1) and [two](http://2)"
    assert extract_links(text) == [("one", "http://1"), ("two", "http://2")]
'''
    (tests / "test_links.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `mdtools/links.py`, fix `extract_links`: extract hyperlink tuples `(text, url)` for Markdown links `[text](url)`, "
        "but ignore images formatted as `![alt](url)`. Read the file, edit with edit_file, test with run_tests, and submit final_answer."
    )
    return "mdtools", prompt


def setup_task_header_normalizer(ws: Path):
    """Task 7: HTTP Header Normalizer."""
    pkg = ws / "httpkit"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .headers import normalize_headers\n', encoding="utf-8")

    code = '''"""HTTP Header Normalizer."""

def normalize_headers(raw_headers: list) -> dict:
    """Normalize headers: lowercase keys, strip whitespace, and combine duplicate keys with comma."""
    normalized = {}
    for key, val in raw_headers:
        k = key.lower().strip()
        v = str(val).strip()
        # BUG: Overwrites duplicate headers instead of combining with ', '
        normalized[k] = v
    return normalized
'''
    (pkg / "headers.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''from httpkit.headers import normalize_headers

def test_basic_headers():
    raw = [("Host", " example.com "), ("Content-Type", "text/html")]
    assert normalize_headers(raw) == {"host": "example.com", "content-type": "text/html"}

def test_duplicate_headers():
    raw = [("Accept", "text/html"), ("accept", "application/json"), ("ACCEPT", "image/webp")]
    assert normalize_headers(raw) == {"accept": "text/html, application/json, image/webp"}
'''
    (tests / "test_headers.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `httpkit/headers.py`, fix `normalize_headers`: keys must be lowercase and stripped of whitespace, "
        "and values stripped of whitespace. When duplicate case-insensitive keys occur, combine their values "
        "with `\", \"` (e.g. 'text/html, application/json') rather than overwriting. "
        "Read the file, edit with edit_file, test with run_tests, and submit final_answer."
    )
    return "httpkit", prompt


def setup_task_semver(ws: Path):
    """Task 8: Semantic Version Comparator."""
    pkg = ws / "versioning"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .semver import compare_versions\n', encoding="utf-8")

    code = '''"""Semantic Versioning."""

def compare_versions(v1: str, v2: str) -> int:
    """Return -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2."""
    # BUG: Lexicographical string comparison causes '1.10.0' < '1.9.0'
    if v1 < v2:
        return -1
    elif v1 > v2:
        return 1
    return 0
'''
    (pkg / "semver.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''from versioning.semver import compare_versions

def test_equal_versions():
    assert compare_versions("1.0.0", "1.0.0") == 0

def test_major_minor_numeric_order():
    # '1.10.0' must be greater than '1.9.0'
    assert compare_versions("1.10.0", "1.9.0") == 1
    assert compare_versions("1.9.0", "1.10.0") == -1

def test_patch_order():
    assert compare_versions("2.0.1", "2.0.15") == -1
    assert compare_versions("2.0.15", "2.0.1") == 1
'''
    (tests / "test_semver.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `versioning/semver.py`, fix `compare_versions`: compare version strings (format 'X.Y.Z') "
        "numerically by parsing each integer component. Return -1 if v1 < v2, 0 if v1 == v2, and 1 if v1 > v2. "
        "Read the file, edit with edit_file, test with run_tests, and submit final_answer."
    )
    return "versioning", prompt


def setup_task_csv_sniffer(ws: Path):
    """Task 9: CSV Delimiter Detector."""
    pkg = ws / "datautils"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .sniffer import detect_delimiter\n', encoding="utf-8")

    code = '''"""CSV Dialect Sniffer."""

def detect_delimiter(sample: str) -> str:
    """Detect delimiter among [',', '\\t', ';']."""
    delimiters = [",", "\\t", ";"]
    # BUG: Naive character counting includes delimiters inside quoted strings
    counts = {d: sample.count(d) for d in delimiters}
    return max(counts, key=counts.get)
'''
    (pkg / "sniffer.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''from datautils.sniffer import detect_delimiter

def test_comma_delimited():
    sample = "name,age,city\\nAlice,30,NY\\nBob,25,LA"
    assert detect_delimiter(sample) == ","

def test_semicolon_with_quoted_commas():
    # Many commas appear inside quotes; real delimiter is semicolon
    sample = 'id;tags;amount\\n1;"alpha,beta,gamma,delta,epsilon";100\\n2;"zeta,eta,theta,iota";200'
    assert detect_delimiter(sample) == ";"

def test_tab_delimited():
    sample = "col1\\tcol2\\tcol3\\nval1\\tval2\\tval3"
    assert detect_delimiter(sample) == "\\t"
'''
    (tests / "test_sniffer.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `datautils/sniffer.py`, fix `detect_delimiter`: detect the most frequent delimiter among `,`, `\\t`, `;` "
        "ignoring characters inside double-quoted string literals `\"...\"` (e.g. by removing quoted sections with re.sub(r'\"[^\"]*\"', '', sample) before counting). "
        "Read the file, edit with edit_file, test with run_tests, and submit final_answer."
    )
    return "datautils", prompt


def setup_task_retry_backoff(ws: Path):
    """Task 10: Exponential Backoff Calculator."""
    pkg = ws / "netutils"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('from .retry import calculate_backoff\n', encoding="utf-8")

    code = '''"""Retry Backoff Calculator."""

def calculate_backoff(attempt: int, base_delay: float = 1.0, factor: float = 2.0, max_delay: float = 30.0) -> float:
    """Calculate exponential backoff delay."""
    # BUG: Fails to validate negative attempts and does not cap at max_delay
    delay = base_delay * (factor ** attempt)
    return delay
'''
    (pkg / "retry.py").write_text(code, encoding="utf-8")

    tests = ws / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    test_code = '''import pytest
from netutils.retry import calculate_backoff

def test_initial_attempts():
    assert calculate_backoff(0) == 1.0
    assert calculate_backoff(1) == 2.0
    assert calculate_backoff(2) == 4.0

def test_max_delay_cap():
    # 1.0 * (2.0 ** 10) = 1024, should be capped at 30.0
    assert calculate_backoff(10, max_delay=30.0) == 30.0

def test_negative_attempt_raises():
    with pytest.raises(ValueError):
        calculate_backoff(-1)
'''
    (tests / "test_retry.py").write_text(test_code, encoding="utf-8")
    prompt = (
        "In `netutils/retry.py`, fix `calculate_backoff`: for attempt `attempt` (0-indexed: 0, 1, ...), "
        "compute `delay = base_delay * (factor ** attempt)` capped at `max_delay` (i.e. `min(delay, max_delay)`). "
        "If `attempt < 0`, raise `ValueError`. Read the file, edit with edit_file, test with run_tests, and submit final_answer."
    )
    return "netutils", prompt


TASK_SETUPS = [
    ("cli_arg_parser", setup_task_cli_parser),
    ("template_formatter", setup_task_template_formatter),
    ("lru_cache", setup_task_lru_cache),
    ("nested_dict_resolver", setup_task_nested_dict),
    ("url_query_encoder", setup_task_url_encoder),
    ("markdown_link_extractor", setup_task_markdown_links),
    ("http_header_normalizer", setup_task_header_normalizer),
    ("semver_comparator", setup_task_semver),
    ("csv_delimiter_detector", setup_task_csv_sniffer),
    ("retry_backoff_calculator", setup_task_retry_backoff),
]


# -----------------------------------------------------------------------------
# Diagnostic Evaluator & Failure Classifier
# -----------------------------------------------------------------------------

@dataclass
class DiagnosticResult:
    task_name: str
    model_name: str
    steps_taken: int
    tokens_consumed: int
    valid_actions: bool
    file_edited: bool
    applicable_patch: bool
    tests_passed: bool
    grader_resolved: bool
    failure_mode: Optional[str] = None
    failure_detail: Optional[str] = None
    edited_files: List[str] = None
    patch_diff: str = ""


def evaluate_task(ws: Path) -> Tuple[bool, str]:
    """Run pytest suite in workspace."""
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=str(ws),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return res.returncode == 0, res.stdout + "\n" + res.stderr


def run_single_calibration(
    task_name: str,
    setup_fn,
    model_cfg: ModelConfig,
    base_dir: Path,
) -> DiagnosticResult:
    """Run one task through the diagnostic ladder."""
    task_dir = base_dir / f"{task_name}_{model_cfg.name.replace(':', '_')}"
    if task_dir.exists():
        shutil.rmtree(task_dir)
    task_dir.mkdir(parents=True, exist_ok=True)

    ws = task_dir / "workspace"
    baseline = task_dir / "baseline"
    
    pkg_name, prompt = setup_fn(ws)
    shutil.copytree(ws, baseline)

    # Initial test must fail
    pre_pass, pre_log = evaluate_task(ws)
    assert not pre_pass, f"Pre-test unexpectedly passed for {task_name}"

    sandbox_cfg = SandboxConfig(image="local", memory="2g", cpus=2, timeout_seconds=60, max_output_chars=5000)
    sandbox = LocalSandbox(ws, sandbox_cfg)
    model = LocalModel(model_cfg)

    task = Task(
        task_id=f"calib_{task_name}",
        group_id=f"group_{pkg_name}",
        source="calibration",
        source_revision="1"*40,
        source_split="dev",
        kind="swe",
        prompt=prompt,
        official_holdout=False,
        repo=pkg_name,
        base_commit="a"*40,
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
    limits = SimpleNamespace(steps=10, completion_tokens=8192, seconds=300)

    session = AgentSession()
    event_store = EventStore(task_dir / "events.sqlite")

    print(f"\n--- CALIBRATING: [{model_cfg.name}] on task: {task_name} ---")
    start_t = time.time()
    phase_res = run_phase(
        task=task,
        session=session,
        model=model,
        sandbox=sandbox,
        store=event_store,
        output=task_dir,
        trial_id=f"{task_name}_{model_cfg.name}",
        actor_name=model_cfg.name,
        phase="draft",
        limits=limits,
        protocol=protocol,
    )
    elapsed = time.time() - start_t

    # --- TIER AUDIT ---
    patch = make_patch(baseline, ws)
    (task_dir / "final.patch").write_text(patch, encoding="utf-8")

    # Tier 1: Action validity
    records = list(event_store.records())
    event_store.close()
    
    all_valid_actions = all(not r.blocked for r in records) and len(records) > 0
    
    # Tier 2: Source files edited
    # Inspect changed paths from diff
    changed_files = [line[6:].strip() for line in patch.splitlines() if line.startswith("+++ b/")]
    existing_src_edited = any(f.startswith(pkg_name) and f.endswith(".py") for f in changed_files)
    
    # Tier 3: Applicable non-empty patch
    applicable_patch = len(patch.strip()) > 0
    
    # Tier 4 & 5: Tests passed and grader resolved
    test_passed, test_out = evaluate_task(ws)
    grader_resolved = test_passed and existing_src_edited

    # Failure Classification
    failure_mode = None
    failure_detail = None
    
    if not all_valid_actions:
        blocked_reasons = [r.block_reason for r in records if r.blocked]
        failure_mode = "INVALID_OUTPUT"
        failure_detail = f"Blocked steps: {blocked_reasons}"
    elif not applicable_patch:
        failure_mode = "NO_EDITS"
        failure_detail = "Agent took actions but made zero file modifications (passive retreat)"
    elif not existing_src_edited:
        failure_mode = "WRONG_FILE"
        failure_detail = f"Edited files outside package ({changed_files}) or created dummy files"
    elif not test_passed:
        failure_mode = "TEST_FAILURE"
        failure_detail = f"Pytest failed after applying edits:\n{test_out[:500]}"

    print(f"Outcome Ladder [{task_name}]:")
    print(f"  Tier 1 (Valid Actions)     : {'PASS' if all_valid_actions else 'FAIL'}")
    print(f"  Tier 2 (Source File Edited): {'PASS' if existing_src_edited else 'FAIL'} (Files: {changed_files})")
    print(f"  Tier 3 (Applicable Patch)  : {'PASS' if applicable_patch else 'FAIL'} ({len(patch)} chars)")
    print(f"  Tier 4 (Tests Passed)      : {'PASS' if test_passed else 'FAIL'}")
    print(f"  Tier 5 (Grader Resolved)   : {'PASS' if grader_resolved else 'FAIL'}")
    if failure_mode:
        print(f"  Failure Diagnosis          : [{failure_mode}] {failure_detail[:120]}")

    return DiagnosticResult(
        task_name=task_name,
        model_name=model_cfg.name,
        steps_taken=phase_res["steps"],
        tokens_consumed=phase_res["known_completion_tokens"],
        valid_actions=all_valid_actions,
        file_edited=existing_src_edited,
        applicable_patch=applicable_patch,
        tests_passed=test_passed,
        grader_resolved=grader_resolved,
        failure_mode=failure_mode,
        failure_detail=failure_detail,
        edited_files=changed_files,
        patch_diff=patch,
    )


def run_full_calibration_suite():
    import argparse
    parser = argparse.ArgumentParser(description="Run Coding Agent Calibration")
    parser.add_argument("--model", type=str, default=None, help="Filter by model name (e.g. qwen2.5-coder:14b)")
    parser.add_argument("--task", type=str, default=None, help="Filter by task name (e.g. url_query_encoder)")
    args, _ = parser.parse_known_args()

    print("================================================================================")
    print(" VERITAS STEP 1-4 CODING AGENT CALIBRATION & DIAGNOSTIC COMPARISON")
    print("================================================================================")

    all_models = [
        ModelConfig(
            name="qwen2.5-coder:7b",
            backend="ollama",
            base_url="http://127.0.0.1:11434",
            temperature=0,
            max_tokens=2048,
        ),
        ModelConfig(
            name="qwen2.5-coder:14b",
            backend="ollama",
            base_url="http://127.0.0.1:11434",
            temperature=0,
            max_tokens=2048,
        ),
    ]

    models_to_test = [m for m in all_models if args.model is None or args.model in m.name]
    tasks_to_test = [t for t in TASK_SETUPS if args.task is None or args.task in t[0]]

    out_base = REPO_ROOT / "artifacts" / "coding_calibration"
    if out_base.exists() and args.model is None and args.task is None:
        shutil.rmtree(out_base)
    out_base.mkdir(parents=True, exist_ok=True)

    summary_records = []

    for model_cfg in models_to_test:
        print(f"\n========================================================================")
        print(f" EVALUATING ACTOR MODEL: {model_cfg.name}")
        print(f"========================================================================")
        
        for task_name, setup_fn in tasks_to_test:
            res = run_single_calibration(task_name, setup_fn, model_cfg, out_base)
            summary_records.append(res)

    # Aggregated Comparative Reporting
    print("\n================================================================================")
    print(" DIAGNOSTIC CALIBRATION SUMMARY & MODEL COMPARISON TABLE")
    print("================================================================================")

    header = f"{'Model':<18} | {'Task':<22} | {'Valid Act':<9} | {'File Edit':<9} | {'Patch App':<9} | {'Tests Pass':<10} | {'Resolved':<8} | {'Failure Mode':<15}"
    print(header)
    print("-" * len(header))

    for r in summary_records:
        fail = r.failure_mode or "NONE (CLEAN)"
        print(f"{r.model_name:<18} | {r.task_name:<22} | {str(r.valid_actions):<9} | {str(r.file_edited):<9} | {str(r.applicable_patch):<9} | {str(r.tests_passed):<10} | {str(r.grader_resolved):<8} | {fail:<15}")

    # Calculate Aggregate Metrics by Model
    print("\n================================================================================")
    print(" AGGREGATE TIER PASS RATES (7B vs 14B)")
    print("================================================================================")
    
    for m in models_to_test:
        m_recs = [r for r in summary_records if r.model_name == m.name]
        n = len(m_recs)
        v_act = sum(r.valid_actions for r in m_recs) / n * 100
        f_edit = sum(r.file_edited for r in m_recs) / n * 100
        p_app = sum(r.applicable_patch for r in m_recs) / n * 100
        t_pass = sum(r.tests_passed for r in m_recs) / n * 100
        g_res = sum(r.grader_resolved for r in m_recs) / n * 100

        print(f"\nActor: {m.name} (N = {n} Tasks):")
        print(f"  Tier 1 - Action Validity Rate    : {v_act:5.1f}% ({sum(r.valid_actions for r in m_recs)}/{n})")
        print(f"  Tier 2 - Target File Edited Rate : {f_edit:5.1f}% ({sum(r.file_edited for r in m_recs)}/{n})")
        print(f"  Tier 3 - Applicable Patch Rate   : {p_app:5.1f}% ({sum(r.applicable_patch for r in m_recs)}/{n})")
        print(f"  Tier 4 - Test Suite Pass Rate    : {t_pass:5.1f}% ({sum(r.tests_passed for r in m_recs)}/{n})")
        print(f"  Tier 5 - Grader Resolved Rate    : {g_res:5.1f}% ({sum(r.grader_resolved for r in m_recs)}/{n})")

    # Serialize Full Diagnostic Report
    report_dict = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "models_evaluated": [m.name for m in models_to_test],
        "tasks": [t[0] for t in TASK_SETUPS],
        "results": [
            {
                "task": r.task_name,
                "model": r.model_name,
                "steps": r.steps_taken,
                "tokens": r.tokens_consumed,
                "valid_actions": r.valid_actions,
                "file_edited": r.file_edited,
                "applicable_patch": r.applicable_patch,
                "tests_passed": r.tests_passed,
                "grader_resolved": r.grader_resolved,
                "failure_mode": r.failure_mode,
                "failure_detail": r.failure_detail,
                "edited_files": r.edited_files,
            }
            for r in summary_records
        ],
    }
    report_path = REPO_ROOT / "artifacts" / "coding_calibration_report.json"
    write_json(report_path, report_dict)
    print(f"\nDetailed Diagnostic JSON saved to: {report_path}")
    print("================================================================================")


if __name__ == "__main__":
    run_full_calibration_suite()
