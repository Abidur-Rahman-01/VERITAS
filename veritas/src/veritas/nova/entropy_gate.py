"""NOVA-VoV Pillar 1: Epistemic Entropy Gate (EEG).

Computes normalized token-level generation entropy directly from the policy
model's logprobs.  Steps with H(x_t) < tau_entropy are INSTANTLY PASSED
with zero verifier tokens.

Evidence basis:
  Kadavath et al. (2022) "Language Models (Mostly) Know What They Know"
  Geifman & El-Yaniv (2017) "Selective Classification for Deep Neural Networks"
"""

from __future__ import annotations

import json
import math
import urllib.request
from dataclasses import dataclass

EPS = 1e-12


def _query_logprobs(
    prompt: str,
    *,
    model: str = "qwen2.5-coder:7b",
    base_url: str = "http://localhost:11434",
    timeout: float = 60.0,
) -> list[list[float]] | None:
    """Return per-token log-probability distributions from Ollama if available."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "logprobs": True,
        "options": {"temperature": 0.0},
    }
    req = urllib.request.Request(
        f"{base_url}/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
            raw = body.get("logprobs") or body.get("prompt_logprobs")
            if raw is None:
                return None
            result: list[list[float]] = []
            for entry in raw:
                if isinstance(entry, dict):
                    top = entry.get("top_logprobs") or {}
                    if top:
                        result.append(list(top.values()))
                    elif "logprob" in entry:
                        result.append([float(entry["logprob"])])
                elif isinstance(entry, (int, float)):
                    result.append([float(entry)])
            return result if result else None
    except Exception:
        return None


def _normalized_entropy(logprob_distributions: list[list[float]]) -> float:
    """Compute mean token-level entropy (nats) across a generation sequence."""
    if not logprob_distributions:
        return float("inf")
    total = 0.0
    for token_logprobs in logprob_distributions:
        if not token_logprobs:
            continue
        probs = [math.exp(lp) for lp in token_logprobs]
        z = sum(probs)
        if z < EPS:
            continue
        probs = [p / z for p in probs]
        h = -sum(p * math.log(p + EPS) for p in probs if p > EPS)
        total += h
    return total / len(logprob_distributions)


def _approx_entropy_from_text(text: str) -> float:
    """Fallback: character-level unigram entropy when logprobs unavailable."""
    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(text)
    return -sum((c / n) * math.log(c / n + EPS) for c in counts.values())


@dataclass
class EpistemicEntropyGate:
    """Zero-cost pre-filter: instantly approve low-entropy (confident) actions.

    Parameters
    ----------
    tau_entropy : float
        Entropy threshold in nats.  Actions with H < tau are passed without
        any downstream verifier call.  Typical range 0.3-1.0 nats.
    model : str
        Ollama model name (must match the policy model).
    base_url : str
        Ollama server URL.
    timeout : float
        HTTP timeout for logprob extraction.
    """

    tau_entropy: float = 0.5
    model: str = "qwen2.5-coder:7b"
    base_url: str = "http://localhost:11434"
    timeout: float = 60.0

    def entropy_of(self, action_text: str) -> float:
        """Measure H(x_t). Uses Ollama logprobs; falls back to char entropy."""
        dists = _query_logprobs(
            action_text, model=self.model, base_url=self.base_url, timeout=self.timeout
        )
        if dists is not None:
            return _normalized_entropy(dists)
        return _approx_entropy_from_text(action_text)

    def should_skip_verification(self, action_text: str) -> tuple[bool, float]:
        """Return (skip_verification, measured_entropy).

        If skip=True, the caller MUST NOT invoke any verifier.
        """
        h = self.entropy_of(action_text)
        return (h < self.tau_entropy, h)
