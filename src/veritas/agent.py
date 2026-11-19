"""The repair agent loop with a harness checkpoint hook.

A checkpoint fires when the repository tree hash changes (a new patch state), up to
``max_checkpoints``. At a checkpoint the harness returns a packet, which is appended as a user
message before the next model call. The whole loop state is serialisable, so a run can be
exported at a checkpoint and continued in several branches from the identical state.
"""

from __future__ import annotations

import copy
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Protocol

from .backend import Backend, ContextExceeded
from .config import AgentConfig, CostConfig
from .sandbox import Sandbox
from .tools import TOOLS, execute

SYSTEM_PROMPT = (
    "You are a software engineer fixing a reported issue in the repository at {workdir}. "
    "Use the tools to inspect code, reproduce the problem, edit source files, and run tests. "
    "Do not modify existing tests to make them pass. Make minimal, correct changes. When the "
    "fix is complete, call `finish`."
)
FORMAT_REMINDER = (
    "Your reply did not contain a valid tool call. Respond with exactly one tool call, "
    "using one of: execute_bash, str_replace_editor, finish."
)
_TOOL_BLOCK = re.compile(r"<tool_call>.*?</tool_call>", re.DOTALL)


@dataclass
class Packet:
    text: str
    included_ids: list[str]
    credits: float = 0.0
    decision: dict = field(default_factory=dict)


@dataclass
class CheckpointState:
    """What the harness sees at a checkpoint. All fields are runtime-visible."""

    index: int
    step: int
    tree_hash: str
    diff: str
    messages: list[dict]
    remaining_credits: float
    recent_logprobs: list[dict]


class Harness(Protocol):
    def __call__(self, state: CheckpointState) -> Packet: ...


@dataclass
class AgentState:
    messages: list[dict]
    step: int = 0
    checkpoints: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    harness_credits: float = 0.0
    sandbox_seconds: float = 0.0
    wall_seconds: float = 0.0
    last_tree: str = ""
    base_tree: str = ""
    format_errors: int = 0
    recent_logprobs: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)

    def credits(self, cost: CostConfig) -> float:
        tokens = self.prompt_tokens + self.completion_tokens
        return (tokens * cost.per_token + self.sandbox_seconds * cost.per_sandbox_second
                + self.harness_credits)

    def clone(self) -> "AgentState":
        return copy.deepcopy(self)

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> "AgentState":
        return cls(**data)


@dataclass
class RunResult:
    state: AgentState
    final_diff: str
    termination: str
    credits: float


def initial_state(problem_statement: str, workdir: str, sandbox: Sandbox) -> AgentState:
    tree = sandbox.tree_hash()
    return AgentState(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(workdir=workdir)},
            {"role": "user", "content": f"<issue>\n{problem_statement}\n</issue>"},
        ],
        last_tree=tree,
        base_tree=tree,
    )


class Agent:
    def __init__(
        self, backend: Backend, sandbox: Sandbox, cfg: AgentConfig, cost: CostConfig,
        harness: Harness | None, seed: int,
        on_checkpoint: Callable[[AgentState, CheckpointState, Packet | None], None] | None = None,
        pre_checkpoint: Callable[[CheckpointState], None] | None = None,
    ):
        self.backend = backend
        self.sandbox = sandbox
        self.cfg = cfg
        self.cost = cost
        self.harness = harness
        self.seed = seed
        self.on_checkpoint = on_checkpoint
        self.pre_checkpoint = pre_checkpoint
        self._run_start = time.monotonic()
        self._wall_base = 0.0

    def _checkpoint(self, state: AgentState, tree: str) -> None:
        """Ask the harness for a packet. ``on_checkpoint`` receives the state *before* the
        packet is appended (the branching point), the harness view, and the packet."""
        state.checkpoints += 1
        diff = self.sandbox.diff()
        view = CheckpointState(
            index=state.checkpoints, step=state.step, tree_hash=tree, diff=diff,
            messages=copy.deepcopy(state.messages),
            remaining_credits=self.cfg.credit_cap - state.credits(self.cost),
            recent_logprobs=list(state.recent_logprobs),
        )
        if self.pre_checkpoint is not None:
            self.pre_checkpoint(view)  # e.g. snapshot the workspace before producers touch it
        before = state.clone()
        before.wall_seconds = self._wall_base + (time.monotonic() - self._run_start)
        packet = self.harness(view) if self.harness is not None else None
        if self.on_checkpoint is not None:
            self.on_checkpoint(before, view, packet)
        if packet is None:
            return
        state.harness_credits += packet.credits
        state.messages.append({"role": "user", "content": packet.text})
        state.events.append({
            "type": "checkpoint", "index": view.index, "step": state.step, "tree": tree,
            "included": packet.included_ids, "decision": packet.decision,
            "credits": packet.credits,
        })

    def deliver_pending_checkpoint(self, state: AgentState) -> None:
        """Used by branches restored at an exported checkpoint: deliver this arm's packet now."""
        start = time.monotonic()
        self._run_start, self._wall_base = start, state.wall_seconds
        state.checkpoints -= 1
        self._checkpoint(state, state.last_tree)
        state.wall_seconds += time.monotonic() - start

    def run(self, state: AgentState) -> RunResult:
        start = time.monotonic()
        self._run_start, self._wall_base = start, state.wall_seconds
        termination = "max_steps"
        while state.step < self.cfg.max_steps:
            if state.credits(self.cost) >= self.cfg.credit_cap:
                termination = "credit_cap"
                break
            if state.wall_seconds + (time.monotonic() - start) >= self.cfg.wall_seconds:
                termination = "wall_cap"
                break
            try:
                gen = self.backend.generate(state.messages, TOOLS,
                                            seed=self.seed * 100003 + state.step)
            except ContextExceeded:
                termination = "context_exceeded"
                break
            state.step += 1
            state.prompt_tokens += gen.prompt_tokens
            state.completion_tokens += gen.completion_tokens
            state.recent_logprobs = (state.recent_logprobs + [{
                "mean_logprob": gen.mean_logprob, "min_logprob": gen.min_logprob,
                "mean_entropy": gen.mean_entropy,
            }])[-3:]
            calls = gen.parsed.calls[:1]  # one action per turn keeps checkpoints well defined
            content = _TOOL_BLOCK.sub("", gen.text).strip()
            if not calls:
                state.messages.append({"role": "assistant", "content": gen.text})
                state.messages.append({"role": "user", "content": FORMAT_REMINDER})
                state.format_errors += 1
                if state.format_errors >= 3:
                    termination = "format_errors"
                    break
                continue
            state.format_errors = 0
            call = calls[0]
            state.messages.append({"role": "assistant", "content": content,
                                   "tool_calls": [call.to_message()]})
            before = self.sandbox.sandbox_seconds
            observation = execute(self.sandbox, call, self.cfg.max_observation_chars)
            state.messages.append({"role": "tool", "tool_call_id": call.call_id,
                                   "name": call.name, "content": observation})
            if call.name == "finish":
                termination = "finished"
                break
            tree = self.sandbox.tree_hash()
            # Only the agent's own tool time is charged here; producers charge their own cost.
            state.sandbox_seconds += self.sandbox.sandbox_seconds - before
            if tree != state.last_tree:
                state.last_tree = tree
                if tree != state.base_tree and state.checkpoints < self.cfg.max_checkpoints:
                    self._checkpoint(state, tree)
        state.wall_seconds += time.monotonic() - start
        final = self.sandbox.diff()
        return RunResult(state, final, termination, state.credits(self.cost))
