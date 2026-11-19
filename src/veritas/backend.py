"""Model backends.

* ``HTTPBackend`` talks to ``veritas serve`` (``hfserver.py``): the single process that owns the GPU
  and provides generation, teacher-forced scoring and hidden states from one set of weights. This
  is the default for every phase, so rollouts, labels and probe features come from identical
  weights and numerics.
* ``OpenAIBackend`` talks to an OpenAI-compatible server (e.g. vLLM) and supports generation and
  token counting only. Use it, if at all, for the screening phase and record that you did.
* ``FakeBackend`` is deterministic and scripted, for tests and smoke runs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Protocol

import httpx

from .config import BackendConfig
from .tools import ParseResult, coerce_structured, parse_tool_calls
from .util import sha256_text


@dataclass
class Generation:
    text: str
    parsed: ParseResult
    prompt_tokens: int
    completion_tokens: int
    mean_logprob: float | None = None
    min_logprob: float | None = None
    mean_entropy: float | None = None
    finish_reason: str = "stop"


@dataclass
class ScoreRequest:
    """log p(reference assistant turn | messages), teacher-forced."""

    messages: list[dict]
    reference: dict
    tools: list[dict] | None = None


@dataclass
class ScoreResult:
    logprob: float
    n_tokens: int
    error: str | None = None


@dataclass
class FeatureResult:
    hidden: list[list[float]] = field(default_factory=list)  # one vector per requested layer
    n_prompt_tokens: int = 0
    error: str | None = None


class Backend(Protocol):
    name: str

    def generate(
        self, messages: list[dict], tools: list[dict] | None, *, seed: int,
        temperature: float | None = None, max_new_tokens: int | None = None,
    ) -> Generation: ...

    def score(self, requests: list[ScoreRequest]) -> list[ScoreResult]: ...

    def features(self, prompts: list[list[dict]], tools: list[dict] | None) -> list[FeatureResult]: ...

    def count_tokens(self, text: str) -> int: ...

    def info(self) -> dict: ...


class BackendUnavailable(RuntimeError):
    pass


class ContextExceeded(RuntimeError):
    pass


class HTTPBackend:
    def __init__(self, cfg: BackendConfig):
        self.cfg = cfg
        self.name = cfg.model
        self.client = httpx.Client(base_url=cfg.base_url, timeout=cfg.request_timeout_seconds)
        self._info: dict | None = None

    def _post(self, path: str, payload: dict) -> dict:
        response = self.client.post(path, json=payload)
        if response.status_code == 413:
            raise ContextExceeded(response.json().get("error", "context exceeded"))
        if response.status_code != 200:
            raise BackendUnavailable(f"{path}: HTTP {response.status_code}: {response.text[:500]}")
        return response.json()

    def info(self) -> dict:
        if self._info is None:
            response = self.client.get("/info")
            response.raise_for_status()
            self._info = response.json()
        return self._info

    def generate(self, messages, tools, *, seed, temperature=None, max_new_tokens=None):
        data = self._post("/generate", {
            "messages": messages, "tools": tools, "seed": seed,
            "temperature": self.cfg.temperature if temperature is None else temperature,
            "top_p": self.cfg.top_p,
            "max_new_tokens": max_new_tokens or self.cfg.max_new_tokens,
        })
        parsed = parse_tool_calls(data["text"])
        return Generation(
            text=data["text"], parsed=parsed, prompt_tokens=data["prompt_tokens"],
            completion_tokens=data["completion_tokens"], mean_logprob=data.get("mean_logprob"),
            min_logprob=data.get("min_logprob"), mean_entropy=data.get("mean_entropy"),
            finish_reason=data.get("finish_reason", "stop"),
        )

    def score(self, requests):
        data = self._post("/score", {"requests": [
            {"messages": r.messages, "reference": r.reference, "tools": r.tools} for r in requests
        ]})
        return [ScoreResult(**row) for row in data["results"]]

    def features(self, prompts, tools):
        data = self._post("/features", {"prompts": prompts, "tools": tools})
        return [FeatureResult(**row) for row in data["results"]]

    def count_tokens(self, text):
        return int(self._post("/tokenize", {"text": text})["count"])


class OpenAIBackend:
    def __init__(self, cfg: BackendConfig):
        self.cfg = cfg
        self.name = cfg.model
        headers = {}
        if cfg.api_key_env:
            headers["Authorization"] = f"Bearer {os.environ[cfg.api_key_env]}"
        self.client = httpx.Client(
            base_url=cfg.base_url.rstrip("/"), timeout=cfg.request_timeout_seconds, headers=headers
        )

    def info(self) -> dict:
        return {"model": self.cfg.model, "backend": "openai", "base_url": self.cfg.base_url}

    def generate(self, messages, tools, *, seed, temperature=None, max_new_tokens=None):
        payload = {
            "model": self.cfg.model, "messages": messages, "seed": seed,
            "temperature": self.cfg.temperature if temperature is None else temperature,
            "top_p": self.cfg.top_p, "max_tokens": max_new_tokens or self.cfg.max_new_tokens,
            "logprobs": True,
        }
        if tools:
            payload["tools"] = tools
        if self.cfg.chat_template_kwargs:
            payload["chat_template_kwargs"] = self.cfg.chat_template_kwargs
        response = self.client.post("/v1/chat/completions", json=payload)
        if response.status_code != 200:
            raise BackendUnavailable(f"HTTP {response.status_code}: {response.text[:500]}")
        data = response.json()
        choice = data["choices"][0]
        message = choice["message"]
        text = message.get("content") or ""
        parsed = coerce_structured(message.get("tool_calls") or [])
        if not parsed.calls:
            parsed = parse_tool_calls(text)
        lps = [t["logprob"] for t in ((choice.get("logprobs") or {}).get("content") or [])]
        usage = data.get("usage", {})
        return Generation(
            text=text, parsed=parsed, prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            mean_logprob=(sum(lps) / len(lps)) if lps else None,
            min_logprob=min(lps) if lps else None, finish_reason=choice.get("finish_reason") or "",
        )

    def score(self, requests):
        raise BackendUnavailable("teacher-forced scoring requires `veritas serve` (HTTPBackend)")

    def features(self, prompts, tools):
        raise BackendUnavailable("hidden-state features require `veritas serve` (HTTPBackend)")

    def count_tokens(self, text):
        response = self.client.post("/tokenize", json={"model": self.cfg.model, "prompt": text})
        response.raise_for_status()
        return int(response.json()["count"])


class FakeBackend:
    """Deterministic backend for tests. ``policy(messages, seed)`` returns the reply text."""

    def __init__(
        self,
        policy: Callable[[list[dict], int], str],
        scorer: Callable[[ScoreRequest], float] | None = None,
        hidden_dim: int = 8,
        n_layers: int = 3,
    ):
        self.name = "fake"
        self.policy = policy
        self.scorer = scorer
        self.hidden_dim = hidden_dim
        self.n_layers = n_layers
        self.calls = 0

    def info(self) -> dict:
        return {"model": "fake", "backend": "fake", "n_feature_layers": self.n_layers}

    def generate(self, messages, tools, *, seed, temperature=None, max_new_tokens=None):
        self.calls += 1
        text = self.policy(messages, seed)
        prompt = sum(self.count_tokens(str(m.get("content") or "")) for m in messages)
        return Generation(
            text=text, parsed=parse_tool_calls(text), prompt_tokens=prompt,
            completion_tokens=self.count_tokens(text), mean_logprob=-0.5, min_logprob=-3.0,
            mean_entropy=1.0,
        )

    def score(self, requests):
        out = []
        for request in requests:
            if self.scorer is None:
                value = -int(sha256_text(repr(request.messages))[:6], 16) / float(1 << 24)
            else:
                value = self.scorer(request)
            out.append(ScoreResult(logprob=value, n_tokens=10))
        return out

    def features(self, prompts, tools):
        results = []
        for prompt in prompts:
            digest = sha256_text(repr(prompt))
            vector = [int(digest[i * 2:i * 2 + 2], 16) / 255.0 for i in range(self.hidden_dim)]
            results.append(FeatureResult(hidden=[vector] * self.n_layers, n_prompt_tokens=1))
        return results

    def count_tokens(self, text):
        return len(text.split())


def make_backend(cfg: BackendConfig) -> Backend:
    if cfg.kind == "hf_server":
        return HTTPBackend(cfg)
    if cfg.kind == "openai":
        return OpenAIBackend(cfg)
    raise ValueError("the fake backend is constructed directly in tests")
