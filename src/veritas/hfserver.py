"""Single-GPU model server: generation, teacher-forced scoring, and hidden-state features.

One process owns the weights. All phases use it, so rollouts, AEV labels and probe features are
computed with identical weights and numerics. Requests are serialised with a lock (one GPU).

Scoring and feature requests that share a conversation prefix reuse its KV cache: the longest
common token prefix of the batch is encoded once, and the cache is cropped back to it after each
request. ``tests/test_hfserver.py`` checks that this equals a full recomputation.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import ServerConfig

EOS_TEXT = ("<|im_end|>", "<|endoftext|>", "<|eot_id|>", "</s>")


def _normalise(messages: list[dict]) -> list[dict]:
    """Chat templates expect tool-call arguments as objects; OpenAI messages carry JSON strings."""
    out = []
    for message in messages:
        message = dict(message)
        if message.get("tool_calls"):
            calls = []
            for call in message["tool_calls"]:
                call = json.loads(json.dumps(call))
                function = call.get("function", {})
                if isinstance(function.get("arguments"), str):
                    try:
                        function["arguments"] = json.loads(function["arguments"] or "{}")
                    except json.JSONDecodeError:
                        pass
                calls.append(call)
            message["tool_calls"] = calls
        if message.get("content") is None:
            message["content"] = ""
        out.append(message)
    return out


def common_prefix_length(sequences: list[list[int]]) -> int:
    if not sequences:
        return 0
    shortest = min(len(s) for s in sequences)
    for i in range(shortest):
        token = sequences[0][i]
        if any(s[i] != token for s in sequences[1:]):
            return i
    return shortest


class HFModel:
    def __init__(self, cfg: ServerConfig):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if not cfg.model_path:
            raise ValueError("server.model_path is required")
        self.torch = torch
        self.cfg = cfg
        self.tokenizer = AutoTokenizer.from_pretrained(cfg.model_path)
        kwargs = {}
        if cfg.quantization == "bnb4":
            from transformers import BitsAndBytesConfig

            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=getattr(torch, cfg.dtype),
            )
        self.model = AutoModelForCausalLM.from_pretrained(
            cfg.model_path,
            torch_dtype=getattr(torch, cfg.dtype),
            attn_implementation=cfg.attn_implementation,
            device_map=cfg.device,
            **kwargs,
        )
        self.model.eval()
        self.device = next(self.model.parameters()).device
        n_layers = int(self.model.config.num_hidden_layers)
        self.n_layers = n_layers
        self.feature_layers = sorted({
            min(n_layers, max(1, round(f * n_layers))) for f in cfg.feature_layer_fractions
        })
        eos = self.model.generation_config.eos_token_id
        self.eos_ids = set(eos if isinstance(eos, list) else [eos]) - {None}
        self.lock = threading.Lock()

    # --- rendering ---------------------------------------------------------------------------
    def render(self, messages, tools, add_generation_prompt: bool) -> str:
        return self.tokenizer.apply_chat_template(
            _normalise(messages), tools=tools or None, tokenize=False,
            add_generation_prompt=add_generation_prompt, **self.cfg.chat_template_kwargs,
        )

    def encode(self, text: str) -> list[int]:
        return self.tokenizer(text, add_special_tokens=False)["input_ids"]

    def info(self) -> dict:
        return {
            "model": self.cfg.model_path, "backend": "hf_server", "dtype": self.cfg.dtype,
            "quantization": self.cfg.quantization,
            "n_layers": self.n_layers, "feature_layers": self.feature_layers,
            "hidden_size": int(self.model.config.hidden_size),
            "max_context_tokens": self.cfg.max_context_tokens,
        }

    # --- generation --------------------------------------------------------------------------
    def generate(self, req: dict) -> dict:
        torch = self.torch
        prompt = self.render(req["messages"], req.get("tools"), True)
        ids = self.encode(prompt)
        max_new = int(req["max_new_tokens"])
        if len(ids) + max_new > self.cfg.max_context_tokens:
            raise OverflowError(f"prompt of {len(ids)} tokens leaves no room to generate")
        temperature = float(req["temperature"])
        torch.manual_seed(int(req["seed"]))
        with torch.inference_mode():
            out = self.model.generate(
                torch.tensor([ids], device=self.device),
                attention_mask=torch.ones((1, len(ids)), dtype=torch.long, device=self.device),
                do_sample=temperature > 0,
                temperature=temperature if temperature > 0 else None,
                top_p=float(req["top_p"]) if temperature > 0 else None,
                top_k=None,
                max_new_tokens=max_new,
                return_dict_in_generate=True,
                output_logits=True,
                pad_token_id=self.tokenizer.pad_token_id or next(iter(self.eos_ids)),
            )
        new_ids = out.sequences[0, len(ids):].tolist()
        logprobs, entropies = [], []
        for step, token in enumerate(new_ids):
            logits = out.logits[step][0].float()
            log_probs = torch.log_softmax(logits, dim=-1)
            logprobs.append(float(log_probs[token]))
            entropies.append(float(-(log_probs.exp() * log_probs).sum()))
        finished = bool(new_ids) and new_ids[-1] in self.eos_ids
        text = self.tokenizer.decode(new_ids, skip_special_tokens=False)
        for marker in EOS_TEXT:
            text = text.replace(marker, "")
        return {
            "text": text, "prompt_tokens": len(ids), "completion_tokens": len(new_ids),
            "mean_logprob": sum(logprobs) / len(logprobs) if logprobs else None,
            "min_logprob": min(logprobs) if logprobs else None,
            "mean_entropy": sum(entropies) / len(entropies) if entropies else None,
            "finish_reason": "stop" if finished else "length",
        }

    # --- shared-prefix forward passes ----------------------------------------------------------
    def _prefix_cache(self, sequences: list[list[int]]):
        """Encode the longest common prefix once; every sequence keeps >= 1 suffix token."""
        from transformers import DynamicCache

        torch = self.torch
        length = min(common_prefix_length(sequences), min(len(s) for s in sequences) - 1)
        cache = DynamicCache()
        if length > 0:
            with torch.inference_mode():
                self.model(
                    torch.tensor([sequences[0][:length]], device=self.device),
                    past_key_values=cache, use_cache=True,
                )
        return length, cache

    def _forward_suffix(self, cache, prefix_len: int, suffix: list[int], hidden: bool):
        torch = self.torch
        with torch.inference_mode():
            out = self.model(
                torch.tensor([suffix], device=self.device),
                past_key_values=cache, use_cache=True, output_hidden_states=hidden,
                cache_position=torch.arange(
                    prefix_len, prefix_len + len(suffix), device=self.device
                ),
            )
        cache.crop(prefix_len)
        return out

    def score(self, req: dict) -> dict:
        torch = self.torch
        prompts, targets, errors = [], [], []
        for item in req["requests"]:
            prompt = self.render(item["messages"], item.get("tools"), True)
            full = self.render(item["messages"] + [item["reference"]], item.get("tools"), False)
            if not full.startswith(prompt):
                errors.append("chat template is not prefix-stable for this reference")
                prompts.append(None)
                targets.append(None)
                continue
            prompt_ids = self.encode(prompt)
            target_ids = self.encode(full[len(prompt):])
            if len(prompt_ids) + len(target_ids) > self.cfg.max_context_tokens:
                errors.append("context exceeded")
                prompts.append(None)
                targets.append(None)
                continue
            errors.append(None)
            prompts.append(prompt_ids)
            targets.append(target_ids)
        valid = [i for i, p in enumerate(prompts) if p is not None]
        results = [{"logprob": float("nan"), "n_tokens": 0, "error": e} for e in errors]
        if not valid:
            return {"results": results}
        sequences = [prompts[i] + targets[i] for i in valid]
        prefix_len, cache = self._prefix_cache(sequences)
        for i in valid:
            sequence = prompts[i] + targets[i]
            out = self._forward_suffix(cache, prefix_len, sequence[prefix_len:], hidden=False)
            logits = out.logits[0]
            # logits[j] predicts suffix token j+1; targets start at suffix index p.
            p = len(prompts[i]) - prefix_len
            total = 0.0
            target = torch.tensor(targets[i], device=self.device)
            for start in range(0, len(targets[i]), 512):
                chunk = logits[p - 1 + start:p - 1 + start + 512].float()
                log_probs = torch.log_softmax(chunk, dim=-1)
                picked = target[start:start + chunk.shape[0]]
                total += float(log_probs.gather(1, picked.unsqueeze(1)).sum())
            results[i] = {"logprob": total, "n_tokens": len(targets[i]), "error": None}
            del out, logits
        return {"results": results}

    def features(self, req: dict) -> dict:
        prompts = [self.encode(self.render(p, req.get("tools"), True)) for p in req["prompts"]]
        results = []
        too_long = [len(p) > self.cfg.max_context_tokens for p in prompts]
        usable = [p for p, bad in zip(prompts, too_long) if not bad]
        prefix_len, cache = self._prefix_cache(usable) if usable else (0, None)
        for ids, bad in zip(prompts, too_long):
            if bad:
                results.append({"hidden": [], "n_prompt_tokens": len(ids), "error": "context"})
                continue
            out = self._forward_suffix(cache, prefix_len, ids[prefix_len:], hidden=True)
            vectors = [
                out.hidden_states[layer][0, -1].float().cpu().tolist()
                for layer in self.feature_layers
            ]
            results.append({"hidden": vectors, "n_prompt_tokens": len(ids), "error": None})
            del out
        return {"results": results}


def make_handler(model: HFModel):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, payload: dict):
            body = json.dumps(payload, allow_nan=True).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

        def do_GET(self):
            if self.path == "/info":
                self._send(200, model.info())
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            routes = {
                "/generate": model.generate, "/score": model.score,
                "/features": model.features,
                "/tokenize": lambda r: {"count": len(model.encode(r["text"]))},
            }
            handler = routes.get(self.path)
            if handler is None:
                self._send(404, {"error": "not found"})
                return
            try:
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with model.lock:
                    self._send(200, handler(request))
            except OverflowError as exc:
                self._send(413, {"error": str(exc)})
            except Exception as exc:  # noqa: BLE001 - report every failure to the client
                self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    return Handler


def serve(cfg: ServerConfig) -> None:
    model = HFModel(cfg)
    server = ThreadingHTTPServer((cfg.host, cfg.port), make_handler(model))
    print(json.dumps({"serving": model.info(), "url": f"http://{cfg.host}:{cfg.port}"}))
    server.serve_forever()
