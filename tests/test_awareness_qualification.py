import json

from veritas.awareness_qualification import qualify_protocol
from veritas.io import write_json


def test_qualification_reports_unavailable_services_without_inference(awareness_setup, tmp_path):
    f = awareness_setup
    config = tmp_path / "config.json"
    write_json(config, f.spec.model_dump())

    def offline(*args, **kwargs):
        raise RuntimeError("Docker unavailable")

    def client(**kwargs):
        raise RuntimeError("Endpoint unavailable")

    # Cohort source uses the same loader as the planner; the prepared fixture lives in memory.
    import veritas.awareness_qualification as qualification
    original = qualification.load_tasks
    qualification.load_tasks = lambda _: [(task, {}) for task in f.tasks]
    try:
        result = qualify_protocol(config, tmp_path / "ready.json", execute=offline,
                                  client_factory=client)
    finally:
        qualification.load_tasks = original
    assert not result["prerequisites_ready"]
    assert result["checks"]["grader_package"]["ok"]
    assert not result["checks"]["docker"]["ok"]
    assert result["inference_exercised"] is False
    assert result["image_digests"] == {}
    assert json.loads((tmp_path / "ready.json").read_text()) == result
