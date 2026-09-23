import json

import httpx
import pytest

from veritas.config import ModelConfig
from veritas.models import LocalModel, parse_object


def test_local_api_contract_no_real_inference():
    def handler(request):
        payload = json.loads(request.content)
        assert payload["model"] == "stub"
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"tool":"final_answer","args":{"answer":"2"}}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            },
        )

    model = LocalModel(ModelConfig(name="stub"), httpx.MockTransport(handler))
    text, usage = model.propose("test")
    assert parse_object(text)["tool"] == "final_answer"
    assert usage.total == 30 and usage.measured
    model.close()


def test_missing_usage_is_not_claimed_measured():
    model = LocalModel(
        ModelConfig(),
        httpx.MockTransport(
            lambda _: httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
        ),
    )
    assert model.complete("s", "u")[1].measured is False
    model.close()


@pytest.mark.parametrize("text", ["[]", 'text {"x":1}', "```json\n{}"])
def test_invalid_json(text):
    with pytest.raises(ValueError):
        parse_object(text)


def test_fenced_json():
    assert parse_object('```json\n{"x":1}\n```') == {"x": 1}
