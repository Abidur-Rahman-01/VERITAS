"""Software fixtures for restrictions; never exported as benchmark data."""
import pytest
import yaml

from veritas.config import ModelConfig
from veritas.data import normalize
from veritas.eligibility import eligible_models, verify_original_tasks
from veritas.io import file_hash, write_json, write_jsonl


def test_exact_cap_rejects_large_unknown_and_misleading_names():
    models = [
        {"name": name, "parameter_count": count, "capabilities": ["completion"]}
        for name, count in [("eight", 8_000_000_000), ("fourteen", 14_000_000_000),
                            ("fake:7b", 20_000_000_000), ("unknown", None),
                            ("rounded:14b", 14_700_000_000)]
    ]
    selected, excluded = eligible_models(ModelConfig(backend="ollama"), models, 14)
    assert [m["name"] for m in selected] == ["eight", "fourteen"]
    assert len(excluded) == 3
    with pytest.raises(ValueError, match="No eligible"):
        eligible_models(ModelConfig(backend="ollama"), models[2:], 14)
    with pytest.raises(ValueError, match="require Ollama"):
        eligible_models(ModelConfig(), models, 14)


def original_fixture(tmp_path):
    spec = {"repo": "software-fixture", "revision": "a" * 40, "adapter": "gsm8k",
            "split": "train", "official_holdout": False}
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"sources": {"fixture": spec}}))
    row = {"question": "Software assertion only", "answer": "#### 2"}
    path = tmp_path / "fixture.jsonl"
    write_jsonl(path, [row])
    receipt = {"spec": spec, "original_data": True, "sha256": file_hash(path)}
    write_json(path.with_suffix(".manifest.json"), receipt)
    return normalize(row, "fixture", spec), {"sources": {"fixture": receipt}}, registry


def test_original_content_checked_not_just_provenance_flag(tmp_path):
    task, manifest, registry = original_fixture(tmp_path)
    evidence = verify_original_tasks([(task, {})], manifest, registry, tmp_path)
    assert evidence["fixture"]["selected_tasks_verified"] == 1
    task.prompt = "Generated replacement"
    with pytest.raises(ValueError, match="differ from original"):
        verify_original_tasks([(task, {})], manifest, registry, tmp_path)


def test_original_receipt_and_checksum_required(tmp_path):
    task, manifest, registry = original_fixture(tmp_path)
    manifest["sources"]["fixture"]["original_data"] = False
    with pytest.raises(ValueError, match="provenance"):
        verify_original_tasks([(task, {})], manifest, registry, tmp_path)
    manifest["sources"]["fixture"]["original_data"] = True
    (tmp_path / "fixture.jsonl").write_text('{}\n')
    with pytest.raises(ValueError, match="integrity"):
        verify_original_tasks([(task, {})], manifest, registry, tmp_path)
