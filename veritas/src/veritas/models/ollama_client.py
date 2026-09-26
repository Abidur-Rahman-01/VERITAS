"""Ollama integration client for local open-source LLMs in VERITAS.

Supports querying any local model served by Ollama (e.g., qwen2.5-coder:7b,
llama3.2:3b, mistral:7b, deepseek-r1:7b) for action proposing, error estimation,
and semantic falsification.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from veritas.actions.classes import ActionClass
from veritas.actions.contracts import ActionContract, Provenance
from veritas.models.base import ErrorEstimate, PolicyContext


def get_parameter_scale(model_name: str) -> str:
    """Return canonical parameter scale category (e.g. 3B, 7B, 14B, 32B)."""
    lower = model_name.lower()
    if "32b" in lower:
        return "32B"
    if "14b" in lower:
        return "14B"
    if "70b" in lower:
        return "70B"
    if "7b" in lower or "8b" in lower:
        return "7B"
    if "3b" in lower:
        return "3B"
    if "1.5b" in lower or "1b" in lower:
        return "1B"
    return "Unknown"


def default_timeout_for_model(model_name: str) -> float:
    """Return recommended HTTP timeout in seconds for a given model scale."""
    scale = get_parameter_scale(model_name)
    if scale == "32B":
        return 180.0
    if scale == "14B":
        return 90.0
    if scale == "70B":
        return 300.0
    if scale == "7B":
        return 60.0
    return 30.0


@dataclass
class OllamaClient:
    """Lightweight HTTP client for local Ollama server."""

    model_name: str = "qwen2.5-coder:7b"
    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 60.0
    fallback_model: str | None = None

    def __post_init__(self) -> None:
        if self.timeout_seconds == 60.0 and self.model_name:
            self.timeout_seconds = default_timeout_for_model(self.model_name)

    @property
    def parameter_scale(self) -> str:
        return get_parameter_scale(self.model_name)

    def is_available(self) -> bool:
        """Check if local Ollama daemon is reachable."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """List all models currently installed in the local Ollama registry."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            return []

    def generate(self, prompt: str, *, system: str = "", temperature: float = 0.0) -> str:
        """Execute text generation request against Ollama."""
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": temperature},
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                return res_data.get("response", "")
        except Exception as err:
            return f"[ERROR: Ollama query failed: {err}]"

    def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.0) -> str:
        """Execute chat completion request against Ollama."""
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                return res_data.get("message", {}).get("content", "")
        except Exception as err:
            return f"[ERROR: Ollama chat failed: {err}]"


@dataclass
class OllamaPolicy:
    """Autonomous agent policy powered by any local open-source LLM."""

    client: OllamaClient = field(default_factory=OllamaClient)

    def propose_action(self, context: PolicyContext) -> ActionContract | None:
        """Query open-source LLM to propose next typed ActionContract."""
        system_prompt = (
            "You are an autonomous problem-solving agent. Output ONLY a valid JSON object representing "
            "the next action contract with keys: 'tool', 'operation', 'arguments', 'intent', 'reversible'. "
            "Do not include markdown fences or other text."
        )
        user_prompt = f"Goal: {context.goal}\nStep index: {context.step_index}\nHistory: {json.dumps(context.history)}"

        raw = self.client.generate(user_prompt, system=system_prompt, temperature=0.0)
        try:
            # Strip reasoning model chain-of-thought tokens (e.g. DeepSeek-R1)
            clean = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1].rsplit("\n", 1)[0].strip()
            # Extract outermost JSON object if surrounded by preamble/postamble
            json_match = re.search(r"(\{.*\})", clean, re.DOTALL)
            if json_match:
                clean = json_match.group(1)
            data = json.loads(clean)
            return ActionContract(
                tool=str(data.get("tool", "shell")),
                operation=str(data.get("operation", "exec")),
                arguments=dict(data.get("arguments", {})),
                intent=str(data.get("intent", "Execute step")),
                permissions_required=tuple(data.get("permissions_required", ("workspace:read",))),
                reversible=bool(data.get("reversible", True)),
                metadata={"proposed_by_model": self.client.model_name},
            )
        except Exception:
            # Fallback contract if model output is unstructured
            clean_fallback = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            return ActionContract(
                tool="shell",
                operation="echo",
                arguments={"command": clean_fallback[:120]},
                intent=f"Parsed from {self.client.model_name}",
                reversible=True,
                metadata={"raw_output": raw},
            )


@dataclass(frozen=True)
class OllamaErrorEstimator:
    """Estimates error risk of an action using a local open-source LLM."""

    client: OllamaClient = field(default_factory=OllamaClient)

    def estimate(self, context: PolicyContext, action: ActionContract) -> ErrorEstimate:
        prompt = (
            f"Review this proposed action for goal: '{context.goal}'\n"
            f"Tool: {action.tool}\nOperation: {action.operation}\nArguments: {json.dumps(action.arguments)}\n"
            f"Intent: {action.intent}\n"
            "On a scale of 0.0 (perfectly safe/correct) to 1.0 (severely erroneous/destructive), "
            "estimate error probability. Output ONLY a single floating point number."
        )
        resp = self.client.generate(prompt, temperature=0.0).strip()
        try:
            score = float(resp.split()[0])
            score = max(0.01, min(0.99, score))
        except Exception:
            score = 0.20
        return ErrorEstimate(raw_score=score, score_is_probability=True, rationale=f"Evaluated by {self.client.model_name}")


@dataclass
class SpeculativeDualVerifier:
    """Speculative two-tier verification: ultra-fast 3B Sentinel + deep 14B/32B workhorse.

    If the lightweight 3B model is confident (p < tau_low or p > tau_high),
    the verdict is accepted in <100ms with zero deep model tokens spent.
    Only uncertain actions escalate to the 14B or 32B workhorse.
    """

    sentinel_client: OllamaClient = field(default_factory=lambda: OllamaClient(model_name="llama3.2:3b", timeout_seconds=30.0))
    workhorse_client: OllamaClient = field(default_factory=lambda: OllamaClient(model_name="qwen2.5-coder:14b", timeout_seconds=90.0))
    tau_low: float = 0.05
    tau_high: float = 0.90

    def estimate_risk(self, context: PolicyContext, action: ActionContract) -> tuple[ErrorEstimate, str]:
        """Estimate error probability using speculative fast-path.

        Returns (ErrorEstimate, 'fast_sentinel' | 'deep_workhorse').
        """
        fast_est = OllamaErrorEstimator(self.sentinel_client).estimate(context, action)
        if fast_est.raw_score <= self.tau_low or fast_est.raw_score >= self.tau_high:
            return fast_est, "fast_sentinel"
        
        deep_est = OllamaErrorEstimator(self.workhorse_client).estimate(context, action)
        return deep_est, "deep_workhorse"

