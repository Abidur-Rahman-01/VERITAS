"""The model server's shared-prefix KV reuse must equal a full recomputation.

Runs on CPU with a tiny public Qwen2-architecture checkpoint (random weights, real Qwen chat
template). Skipped when torch/transformers are not installed or the model cannot be downloaded.
"""

import json
import os

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("transformers")

from veritas.config import ServerConfig  # noqa: E402
from veritas.hfserver import HFModel, common_prefix_length  # noqa: E402
from veritas.tools import TOOLS  # noqa: E402

TINY = os.environ.get("VERITAS_TINY_MODEL", "trl-internal-testing/tiny-Qwen2ForCausalLM-2.5")


@pytest.fixture(scope="module")
def model():
    try:
        return HFModel(ServerConfig(model_path=TINY, dtype="float32", device="cpu",
                                    attn_implementation="eager", max_context_tokens=4096))
    except Exception as exc:  # noqa: BLE001 - offline machines skip
        pytest.skip(f"tiny model unavailable: {exc}")


def full_logprob(model: HFModel, prompt_ids, target_ids) -> float:
    ids = torch.tensor([prompt_ids + target_ids])
    with torch.inference_mode():
        logits = model.model(ids).logits[0].float()
    log_probs = torch.log_softmax(logits, dim=-1)
    start = len(prompt_ids)
    return float(sum(log_probs[start - 1 + k, t] for k, t in enumerate(target_ids)))


def conversation(packet: str):
    return [
        {"role": "system", "content": "You fix bugs."},
        {"role": "user", "content": "<issue>add is wrong</issue>"},
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": "c0", "type": "function",
            "function": {"name": "execute_bash", "arguments": json.dumps({"command": "ls"})}}]},
        {"role": "tool", "tool_call_id": "c0", "name": "execute_bash", "content": "calc.py"},
        {"role": "user", "content": packet},
    ]


REFERENCE = {"role": "assistant", "content": "", "tool_calls": [{
    "id": "r0", "type": "function", "function": {"name": "str_replace_editor", "arguments": json.dumps(
        {"command": "str_replace", "path": "calc.py", "old_str": "a - b", "new_str": "a + b"})}}]}


def test_common_prefix_length():
    assert common_prefix_length([[1, 2, 3], [1, 2, 4], [1, 2]]) == 2
    assert common_prefix_length([[5], [6]]) == 0


def test_score_equals_full_recompute(model):
    packets = ["[HARNESS] neutral", "[HARNESS EVIDENCE] Test add fails.", "[HARNESS EVIDENCE] x"]
    requests = [{"messages": conversation(p), "reference": REFERENCE, "tools": TOOLS}
                for p in packets]
    results = model.score({"requests": requests})["results"]
    for request, result in zip(requests, results):
        assert result["error"] is None
        prompt = model.render(request["messages"], TOOLS, True)
        full = model.render(request["messages"] + [REFERENCE], TOOLS, False)
        expected = full_logprob(model, model.encode(prompt), model.encode(full[len(prompt):]))
        assert result["logprob"] == pytest.approx(expected, rel=1e-4, abs=1e-3)
        assert result["n_tokens"] == len(model.encode(full[len(prompt):]))


def test_features_equal_full_forward(model):
    prompts = [conversation("[HARNESS] neutral"), conversation("[HARNESS EVIDENCE] fails")]
    results = model.features({"prompts": prompts, "tools": TOOLS})["results"]
    for prompt, result in zip(prompts, results):
        ids = torch.tensor([model.encode(model.render(prompt, TOOLS, True))])
        with torch.inference_mode():
            out = model.model(ids, output_hidden_states=True)
        for layer, vector in zip(model.feature_layers, result["hidden"]):
            expected = out.hidden_states[layer][0, -1].float().tolist()
            assert vector == pytest.approx(expected, rel=1e-3, abs=1e-4)


def test_generate_is_seeded(model):
    request = {"messages": conversation("[HARNESS] neutral"), "tools": TOOLS, "seed": 3,
               "temperature": 0.7, "top_p": 0.95, "max_new_tokens": 8}
    a, b = model.generate(request), model.generate(request)
    assert a["text"] == b["text"] and a["completion_tokens"] <= 8
    assert a["mean_logprob"] is None or a["mean_logprob"] <= 0
