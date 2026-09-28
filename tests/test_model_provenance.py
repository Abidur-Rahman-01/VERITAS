import base64
import json

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from veritas.config import ModelConfig
from veritas.io import canonical, digest
from veritas.models import LocalModel, ModelOutputError


@pytest.mark.parametrize("backend", ["openai_compatible", "ollama"])
@pytest.mark.parametrize("failure", [None, "missing", "revision", "nonce", "request_sha256",
                                    "content_sha256", "signature"])
def test_seed_and_request_bound_attestation(backend, failure):
    key = Ed25519PrivateKey.generate()
    config = ModelConfig(backend=backend, name="fixture", sampling_seed=17,
                        attestation={"public_key_hex": key.public_key().public_bytes_raw().hex(),
                                     "revision": "fixture-revision"})

    def handler(request):
        payload = json.loads(request.content)
        options = payload["options"] if backend == "ollama" else payload
        assert options["seed"] == 17
        assert (options["num_predict"] if backend == "ollama" else options["max_tokens"]) == 11
        content = '{"ok": true}'
        body = {"revision": "fixture-revision", "nonce": request.headers["X-Veritas-Nonce"],
                "request_sha256": digest(payload), "content_sha256": digest(content)}
        if failure in body:
            body[failure] = "different"
        signature = base64.b64encode(key.sign(canonical(body))).decode()
        data = {"model": "fixture", "system_fingerprint": "not-a-revision",
                "veritas_usage": {"cpu_seconds": 1.25, "gpu_seconds": 2.5, "source": "fixture"}}
        if backend == "ollama":
            data.update(message={"content": content}, prompt_eval_count=7, eval_count=3)
        else:
            data.update(choices=[{"message": {"content": content}}],
                        usage={"prompt_tokens": 7, "completion_tokens": 3})
        if failure != "missing":
            data["veritas_attestation"] = {**body, "signature":
                                          "invalid" if failure == "signature" else signature}
        return httpx.Response(200, json=data)

    model = LocalModel(config, httpx.MockTransport(handler))
    try:
        if failure:
            with pytest.raises(ModelOutputError) as error:
                model.complete("system", "user", max_tokens=11)
            assert error.value.usage.total == 10
            assert error.value.usage.measured
            assert not error.value.usage.provenance["revision_verified"]
        else:
            _, usage = model.complete("system", "user", max_tokens=11)
            assert usage.provenance["revision_verified"]
            assert usage.provenance["sampling_seed_requested"] == 17
            assert usage.provenance["sampling_seed_honored"] is None
            assert usage.cpu_seconds == 1.25 and usage.gpu_seconds == 2.5
            assert usage.resource_source == "provider_reported: fixture"
    finally:
        model.close()


def test_ordinary_model_identifier_is_not_verified_revision():
    def handler(request):
        assert "seed" not in json.loads(request.content)
        assert "X-Veritas-Nonce" not in request.headers
        return httpx.Response(200, json={"model": "revision-looking-name",
            "system_fingerprint": "some-fingerprint", "choices": [{"message": {"content": "{}"}}]})

    model = LocalModel(ModelConfig(), httpx.MockTransport(handler))
    try:
        _, usage = model.complete("system", "user")
        assert not usage.provenance["revision_verified"]
        assert usage.cpu_seconds is None and usage.gpu_seconds is None
    finally:
        model.close()


@pytest.mark.parametrize("seed", [True, "1", -1, 2**63])
def test_invalid_sampling_seeds_are_rejected(seed):
    with pytest.raises(ValueError):
        ModelConfig(sampling_seed=seed)


def test_transformers_does_not_silently_ignore_provenance_settings():
    with pytest.raises(ValueError, match="HTTP backend"):
        ModelConfig(backend="transformers", sampling_seed=1)
