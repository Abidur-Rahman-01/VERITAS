"""Evidence producers F1–F7. They use only runtime-visible inputs.

F1-F4 are observed (they come from running code in the sandbox). F5-F7 are model opinions
produced by the resident actor model, labelled as such, with their tokens charged.
"""

from __future__ import annotations

import ast
import difflib
import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .backend import Backend
from .config import CostConfig, EvidenceConfig
from .evidence import EvidenceItem
from .sandbox import Sandbox
from .tasks import is_test_path, patch_files
from .util import sha256_text, truncate_middle

SUMMARY = re.compile(r"^(PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED)\s+(\S+)(?:\s+-\s+(.*))?$")
LOCATION = re.compile(r"^(\S+\.py):(\d+): (.*)$")
LOCAL_VAR = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s+= (.*)$")
SECTION = re.compile(r"^_{3,} (.+?) _{3,}$")
THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
VERB = {"FAILED": "fails", "ERROR": "errors during setup or collection"}


@dataclass
class ProducerContext:
    task_id: str
    problem_statement: str
    checkpoint_id: str
    tree_hash: str
    environment_hash: str
    diff: str
    seed: int = 0


@dataclass
class TestRun:
    command: str
    exit_code: int
    output: str
    seconds: float
    outcomes: dict[str, str] = field(default_factory=dict)
    messages: dict[str, str] = field(default_factory=dict)

    @property
    def failed(self) -> list[str]:
        return [t for t, o in self.outcomes.items() if o in ("FAILED", "ERROR")]

    @property
    def passed(self) -> list[str]:
        return [t for t, o in self.outcomes.items() if o == "PASSED"]


@dataclass
class ProducerOutput:
    items: list[EvidenceItem]
    credits: float
    tokens: int
    sandbox_seconds: float
    errors: list[str]


def parse_summary(output: str) -> tuple[dict[str, str], dict[str, str]]:
    outcomes: dict[str, str] = {}
    messages: dict[str, str] = {}
    for line in output.splitlines():
        match = SUMMARY.match(line.strip())
        if match:
            status, test, message = match.groups()
            if "::" not in test:
                continue
            outcomes[test] = status
            if message:
                messages[test] = message.strip()
    return outcomes, messages


def failure_sections(output: str) -> dict[str, str]:
    """Map pytest section titles ('test_x', 'TestC.test_y[p]') to their traceback text."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in output.splitlines():
        match = SECTION.match(line.strip())
        if match:
            title = match.group(1).strip()
            current = None if title.lower().startswith(("short test summary", "warnings")) else title
            if current:
                sections[current] = []
            continue
        if line.startswith("=" * 5):
            current = None
            continue
        if current:
            sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def section_for(test_id: str, sections: dict[str, str]) -> str:
    parts = test_id.split("::")[1:]
    candidates = [".".join(parts), parts[-1] if parts else ""]
    for key in candidates:
        if key and key in sections:
            return sections[key]
    return ""


def last_frames(output: str) -> list[tuple[str, list[str]]]:
    """(location, locals) per frame from `--showlocals --tb=long` output, in order."""
    frames: list[tuple[str, list[str]]] = []
    pending: list[str] = []
    for line in output.splitlines():
        if LOCAL_VAR.match(line):
            pending.append(line.rstrip())
            continue
        match = LOCATION.match(line.strip())
        if match:
            frames.append((f"{match.group(1)}:{match.group(2)}", pending))
            pending = []
    return frames


def test_functions(source: str) -> dict[str, str]:
    """Test function sources keyed by 'name' and 'Class.name'."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    found: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            found[node.name] = ast.get_source_segment(source, node) or ""
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name.startswith(
                    "test"
                ):
                    found[f"{node.name}.{sub.name}"] = ast.get_source_segment(source, sub) or ""
    return found


def _function_key(test_id: str) -> str:
    parts = test_id.split("::")[1:]
    return re.sub(r"\[.*\]$", "", ".".join(parts))


def extract_json(text: str) -> dict | None:
    text = THINK.sub("", text)
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for end in range(start, len(text)):
            char = text[end]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start:end + 1])
                        return value if isinstance(value, dict) else None
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


class Producers:
    def __init__(self, sandbox: Sandbox, backend: Backend, ev_cfg: EvidenceConfig,
                 cost_cfg: CostConfig):
        self.sandbox = sandbox
        self.backend = backend
        self.cfg = ev_cfg
        self.cost = cost_cfg

    # --- shared sandbox runs -----------------------------------------------------------------
    def related_tests(self, diff: str) -> list[str]:
        sources = [p for p in patch_files(diff) if p.endswith(".py") and not is_test_path(p)]
        found: list[str] = []
        for path in sources:
            stem = PurePosixPath(path).stem
            if stem == "__init__":
                stem = PurePosixPath(path).parent.name
            if not stem:
                continue
            pattern = shlex.quote(f"(^|/)(test_{stem}|{stem}_test|test_{stem}s)\\.py$")
            listed = self.sandbox.exec(f"git ls-files '*.py' | grep -E {pattern} | head -5")
            found += [x for x in listed.output.split() if x]
            # POSIX ERE only (no word-boundary escapes): GNU and BSD grep must agree.
            module = f"([A-Za-z0-9_]+\\.)*{re.escape(stem)}([[:space:]]|,|\\.|$)"
            grep = self.sandbox.exec(
                "git grep -l -E "
                + shlex.quote(f"(import|from)[[:space:]]+{module}")
                + " -- '*test*.py' | head -5"
            )
            found += [x for x in grep.output.split() if x and is_test_path(x)]
        unique: list[str] = []
        for path in found:
            if path not in unique:
                unique.append(path)
        return unique[:5]

    def run_tests(self, targets: list[str], extra: str = "--tb=short") -> TestRun:
        quoted = " ".join(shlex.quote(t) for t in targets)
        command = f"python -m pytest -rA -q -p no:cacheprovider {extra} {quoted}"
        result = self.sandbox.exec(command, timeout=self.cfg.test_timeout_seconds)
        outcomes, messages = parse_summary(result.output)
        return TestRun(command, result.exit_code, result.output, result.seconds, outcomes,
                       messages)

    # --- producers ---------------------------------------------------------------------------
    def produce(self, ctx: ProducerContext) -> ProducerOutput:
        items: list[EvidenceItem] = []
        errors: list[str] = []
        tokens = 0
        seconds_before = self.sandbox.sandbox_seconds
        families = set(self.cfg.families)
        changed = [p for p in patch_files(ctx.diff) if p.endswith(".py")]
        run: TestRun | None = None
        if families & {"F1", "F2", "F3", "F4"}:
            items += self._syntax(ctx, changed) if "F1" in families else []
            tests = self.related_tests(ctx.diff)
            if tests:
                run = self.run_tests(tests)
        if run is not None:
            if "F1" in families:
                items += self._f1(ctx, run)
            if "F2" in families:
                items += self._f2(ctx, run)
            if "F3" in families:
                items += self._f3(ctx, run)
            if "F4" in families and run.failed:
                items += self._f4(ctx, run)
        failing_summary = "\n".join(
            f"{t}: {run.messages.get(t, run.outcomes[t])}" for t in (run.failed if run else [])
        )[:2000]
        for family, builder in (("F5", self._f5), ("F6", self._f6), ("F7", self._f7)):
            if family in families:
                try:
                    item, used = builder(ctx, failing_summary)
                    tokens += used
                    if item is not None:
                        items.append(item)
                except Exception as exc:  # noqa: BLE001 - a failed producer yields no item
                    errors.append(f"{family}: {type(exc).__name__}: {exc}")
        if self.sandbox.tree_hash() != ctx.tree_hash:
            # Producers must not change the agent's workspace (e.g. tests that write files).
            self.sandbox.restore_tree(ctx.tree_hash)
            errors.append("producers modified the workspace; restored")
        seconds = self.sandbox.sandbox_seconds - seconds_before
        credits = tokens * self.cost.per_token + seconds * self.cost.per_sandbox_second
        if items:
            share = credits / len(items)
            for item in items:
                item.cost_credits = share
        return ProducerOutput(items, credits, tokens, seconds, errors)

    def _item(self, ctx: ProducerContext, **fields) -> EvidenceItem:
        observed = truncate_middle(fields.pop("observed", ""), self.cfg.max_item_chars)
        return EvidenceItem(
            task_id=ctx.task_id, checkpoint_id=ctx.checkpoint_id, patch_hash=ctx.tree_hash,
            environment_hash=ctx.environment_hash, observed=observed,
            raw_artifact_hash=sha256_text(observed), **fields,
        )

    def _syntax(self, ctx, changed: list[str]) -> list[EvidenceItem]:
        if not changed:
            return []
        quoted = " ".join(shlex.quote(p) for p in changed)
        result = self.sandbox.exec(
            f"for f in {quoted}; do [ -f \"$f\" ] && python -m py_compile \"$f\"; done"
        )
        if result.exit_code == 0:
            return []
        return [self._item(
            ctx, family="F1", source="py_compile", basis="observed",
            command="python -m py_compile <changed files>",
            claim="A changed file does not compile.", observed=result.output,
            affected_files=changed, severity=1.0,
        )]

    def _f1(self, ctx, run: TestRun) -> list[EvidenceItem]:
        files = sorted({t.split("::")[0] for t in run.outcomes})
        if run.exit_code == 5 or (not run.outcomes and run.exit_code == 0):
            return []
        if run.exit_code not in (0, 1):
            return [self._item(
                ctx, family="F1", source="pytest", basis="observed", command=run.command,
                claim="The related tests could not run (collection or usage error, or timeout).",
                observed=run.output[-3000:], severity=0.8,
            )]
        if not run.failed:
            return [self._item(
                ctx, family="F1", source="pytest", basis="observed", command=run.command,
                claim=f"All {len(run.passed)} related tests pass.",
                observed="Files: " + ", ".join(files), tests=run.passed[:20], severity=0.1,
            )]
        items = []
        for test in run.failed[: self.cfg.max_items_per_family]:
            items.append(self._item(
                ctx, family="F1", source="pytest", basis="observed", command=run.command,
                claim=f"Test {test} {VERB[run.outcomes[test]]}.", location=test,
                observed=run.messages.get(test, ""), tests=[test],
                affected_files=[test.split("::")[0]], severity=0.9,
            ))
        return items

    def _f2(self, ctx, run: TestRun) -> list[EvidenceItem]:
        sections = failure_sections(run.output)
        items = []
        for test in run.failed[: self.cfg.max_items_per_family]:
            text = section_for(test, sections)
            if not text:
                continue
            locations = [m.group(1) + ":" + m.group(2) for m in
                         (LOCATION.match(x.strip()) for x in text.splitlines()) if m]
            source_locs = [loc for loc in locations if not is_test_path(loc.split(":")[0])]
            location = (source_locs or locations or [test])[-1]
            items.append(self._item(
                ctx, family="F2", source="pytest", basis="observed", command=run.command,
                claim=f"Traceback of the failure in {test}.", location=location,
                observed=text, tests=[test], affected_files=[location.split(":")[0]],
                severity=0.8,
            ))
        return items

    def _f3(self, ctx, run: TestRun) -> list[EvidenceItem]:
        items = []
        for test in run.failed[: self.cfg.max_items_per_family]:
            path = test.split("::")[0]
            source = self.sandbox.read_file(path)
            if not source:
                continue
            functions = test_functions(source)
            failing_src = functions.get(_function_key(test))
            if not failing_src:
                continue
            best, best_ratio = None, -1.0
            for other in run.passed:
                if other.split("::")[0] != path:
                    continue
                other_src = functions.get(_function_key(other))
                if not other_src or other_src == failing_src:
                    continue
                ratio = difflib.SequenceMatcher(None, failing_src, other_src).ratio()
                if ratio > best_ratio:
                    best, best_ratio = other, ratio
            if best is None:
                continue
            observed = (f"FAILING {test}:\n{failing_src}\n\n"
                        f"PASSING {best}:\n{functions[_function_key(best)]}")
            items.append(self._item(
                ctx, family="F3", source="pytest+ast", basis="observed", command=run.command,
                claim=f"{test} fails while the most similar test {best} passes.",
                location=test, observed=observed, tests=[test, best], affected_files=[path],
                severity=0.7,
            ))
        return items

    def _f4(self, ctx, run: TestRun) -> list[EvidenceItem]:
        test = run.failed[0]
        rerun = self.run_tests([test], extra="-x --tb=long --showlocals")
        frames = [(loc, local) for loc, local in last_frames(rerun.output) if local]
        if not frames:
            return []
        source_frames = [f for f in frames if not is_test_path(f[0].split(":")[0])]
        location, local = (source_frames or frames)[-1]
        return [self._item(
            ctx, family="F4", source="pytest --showlocals", basis="observed",
            command=rerun.command, claim=f"Runtime values at {location} when {test} fails.",
            location=location, observed="\n".join(local), tests=[test],
            affected_files=[location.split(":")[0]], severity=0.6,
        )]

    # --- model-opinion producers (resident model, temperature 0) -----------------------------
    def _ask(self, ctx, instruction: str, failing: str) -> tuple[dict | None, int]:
        files = self.sandbox.exec("git ls-files '*.py' | head -300").output
        prompt = (
            f"Issue:\n{truncate_middle(ctx.problem_statement, 4000)}\n\n"
            f"Current patch (may be empty or wrong):\n{truncate_middle(ctx.diff, 4000) or '(none)'}"
            f"\n\nFailing related tests:\n{failing or '(none observed)'}\n\n"
            f"Python files:\n{truncate_middle(files, 3000)}\n\n{instruction}\n"
            "Reply with one JSON object and nothing else."
        )
        messages = [
            {"role": "system", "content": "You are a careful software debugging assistant."},
            {"role": "user", "content": prompt},
        ]
        gen = self.backend.generate(
            messages, None, seed=ctx.seed, temperature=0.0,
            max_new_tokens=self.cfg.producer_max_new_tokens,
        )
        return extract_json(gen.text), gen.prompt_tokens + gen.completion_tokens

    def _f5(self, ctx, failing):
        data, used = self._ask(
            ctx,
            'Locate the fault. JSON keys: "file" (path), "function" (name or ""), '
            '"root_cause" (one or two sentences).',
            failing,
        )
        if not data or not data.get("file") or not data.get("root_cause"):
            return None, used
        location = str(data["file"]) + (f"::{data['function']}" if data.get("function") else "")
        return self._item(
            ctx, family="F5", source="actor-localizer", basis="model_opinion",
            claim=str(data["root_cause"])[:600], location=location,
            affected_files=[str(data["file"])], severity=0.5,
        ), used

    def _f6(self, ctx, failing):
        data, used = self._ask(
            ctx, 'Propose a repair plan. JSON key: "plan" (list of at most 4 short steps).', failing
        )
        plan = data.get("plan") if data else None
        if not isinstance(plan, list) or not plan:
            return None, used
        steps = "\n".join(f"{i + 1}. {str(s)[:300]}" for i, s in enumerate(plan[:4]))
        return self._item(
            ctx, family="F6", source="actor-planner", basis="model_opinion",
            claim="Suggested repair plan.", observed=steps, severity=0.4,
        ), used

    def _f7(self, ctx, failing):
        data, used = self._ask(
            ctx,
            'Write acceptance criteria a correct fix must satisfy. JSON key: "criteria" '
            "(list of 3 to 5 short, checkable statements).",
            failing,
        )
        criteria = data.get("criteria") if data else None
        if not isinstance(criteria, list) or not criteria:
            return None, used
        text = "\n".join(f"- {str(c)[:300]}" for c in criteria[:5])
        return self._item(
            ctx, family="F7", source="actor-rubric", basis="model_opinion",
            claim="Acceptance criteria for a correct fix.", observed=text, severity=0.3,
        ), used
