import json

from veritas.awareness import ReviewLimits
from veritas.patch_review import boundary_message, make_packet, review_patch
from veritas.schema import Usage


def test_public_review_packet_is_deterministic_and_bounded(awareness_setup, tmp_path):
    task = awareness_setup.tasks[0].model_copy(update={"prompt": "issue "*4000})
    (tmp_path / "value.py").write_text("x"*8000)
    patch = "--- a/value.py\n+++ b/value.py\n" + "+value = 1\n"*1000
    limits = ReviewLimits(input_chars=1000)
    packet = make_packet(task, patch, tmp_path, [], limits)
    assert packet == make_packet(task, patch, tmp_path, [], limits)
    assert len(json.dumps(packet, ensure_ascii=False)) <= 1000
    assert packet["truncated"]
    assert "PRIVATE_GOLD" not in json.dumps(packet) and "PRIVATE_TEST" not in json.dumps(packet)
    assert "actor_id" not in packet and "actual_assignment" not in packet


def test_malformed_review_is_one_error_without_repair_call():
    class Reviewer:
        calls = 0

        def complete(self, *args, **kwargs):
            self.calls += 1
            return '{"verdict":"PASS","findings":[{"path":"x","explanation":"bad"}]}', Usage(
                prompt_tokens=2, completion_tokens=3)

    model = Reviewer()
    record = review_patch({"issue": "fixture"}, "patch", model, ReviewLimits())
    assert model.calls == 1 and record.verdict == "ERROR"
    assert record.attempted and not record.completed
    assert record.usage.completion_tokens == 3
    assert "unavailable" in boundary_message(record)


def test_pass_is_explicit_feedback():
    class Reviewer:
        def complete(self, *args, **kwargs):
            return '{"verdict":"PASS","findings":[]}', Usage(completion_tokens=3)

    record = review_patch({"issue": "fixture"}, "patch", Reviewer(), ReviewLimits())
    assert record.completed and record.verdict == "PASS"
    assert '"verdict": "PASS"' in boundary_message(record)
