import json

import numpy as np
import pytest
from pydantic import ValidationError

from veritas.config import DataConfig, SplitConfig, StudyConfig
from veritas.evidence import NEUTRAL_PACKET, EvidenceBank, EvidenceItem, render_packet
from veritas.features import ITEM_COLUMNS, LOGPROB_COLUMNS, OUTCOME_PLANE_WORDS, STATE_COLUMNS
from veritas.ledger import Ledger, LedgerCorrupt
from veritas.stats import holm, mcnemar_exact, mcnemar_pairs_needed, paired_contrast
from veritas.tasks import eligibility, load_tasks, patch_files, split_by_repository, task_from_row
from veritas.tools import parse_tool_calls
from veritas.util import truncate_middle


def test_ledger_chain_and_tamper_detection(tmp_path):
    ledger = Ledger(tmp_path / "l.jsonl")
    ledger.append("a", x=1)
    ledger.mark_done("unit", "k1")
    assert ledger.completed("unit") == {"k1"}
    Ledger(tmp_path / "l.jsonl")  # re-open verifies
    lines = (tmp_path / "l.jsonl").read_text().splitlines()
    event = json.loads(lines[0])
    event["x"] = 2
    lines[0] = json.dumps(event)
    (tmp_path / "l.jsonl").write_text("\n".join(lines) + "\n")
    with pytest.raises(LedgerCorrupt):
        Ledger(tmp_path / "l.jsonl")


def test_patch_files_and_task_normalisation(repo_rows):
    row = dict(repo_rows[0])
    assert patch_files(row["patch"]) == ["calc.py"]
    row["FAIL_TO_PASS"] = json.dumps(row["FAIL_TO_PASS"])  # SWE-bench Verified stores strings
    task = task_from_row(row, "swe_rebench")
    assert task.fail_to_pass[0] == "tests/test_hidden.py::test_add_hidden"


def test_eligibility_rules(repo_rows):
    cfg = DataConfig(created_after="2025-01-01")
    assert eligibility(repo_rows[0], cfg, set()) is None
    assert eligibility(repo_rows[0], cfg, {repo_rows[0]["instance_id"]}) == "excluded_id"
    old = dict(repo_rows[0], created_at="2020-01-01")
    assert eligibility(old, cfg, set()) == "before_cutoff"
    other = dict(repo_rows[0], install_config={"log_parser": "parse_log_django"})
    assert eligibility(other, cfg, set()) == "non_pytest_parser"


def test_split_is_repository_disjoint_and_deterministic():
    repos = {f"r{i}": (i % 4) + 1 for i in range(40)}
    a = split_by_repository(repos, SplitConfig())
    b = split_by_repository(repos, SplitConfig())
    assert a == b
    totals = {s: sum(repos[r] for r in a if a[r] == s) for s in ("train", "dev", "confirm")}
    total = sum(repos.values())
    assert abs(totals["train"] / total - 0.45) < 0.05
    assert abs(totals["confirm"] / total - 0.45) < 0.05


def test_study_dataset_if_fetched():
    """After `veritas fetch-data`, the pinned dataset must give the documented pool."""
    from pathlib import Path

    from veritas.config import load_config

    data = load_config("configs/study.yaml").data
    if not (Path(data.dataset_path).exists() and Path(data.exclude_ids_path).exists()):
        pytest.skip("dataset not fetched (veritas fetch-data --config configs/study.yaml)")
    tasks, summary = load_tasks(data)
    assert summary["eligible"] == 193 and len({t.repo for t in tasks}) == 115
    assert all(t.created_at[:10] >= "2025-05-01" and t.fail_to_pass for t in tasks)
    assert all(t.image.startswith("docker.io/swerebenchv2/") for t in tasks)


def test_parse_tool_calls_formats():
    tagged = 'x <tool_call>{"name": "finish", "arguments": {}}</tool_call>'
    assert parse_tool_calls(tagged).calls[0].name == "finish"
    fenced = '```json\n{"name": "execute_bash", "arguments": {"command": "ls"}}\n```'
    assert parse_tool_calls(fenced).calls[0].arguments == {"command": "ls"}
    bad = '<tool_call>{"name": "rm_rf", "arguments": {}}</tool_call>'
    parsed = parse_tool_calls(bad)
    assert not parsed.calls and parsed.errors


def _item(family="F1", tree="t1", env="e", **kw):
    return EvidenceItem(family=family, source="pytest", basis="observed", patch_hash=tree,
                        environment_hash=env, claim=kw.pop("claim", f"claim {family}"), **kw)


def test_evidence_validity_rule():
    bank = EvidenceBank()
    bank.add(_item(tree="t1"))
    bank.add(_item(family="F2", tree="t2"))
    assert len(bank.current("t2", "e")) == 1
    assert bank.expire_except("t2", "e") == 1
    assert bank.current("t1", "e") == []
    assert len(bank.current("t2", "e2")) == 0  # environment change also invalidates


def test_render_packet_respects_cap_and_neutral():
    def count(text):
        return len(text.split())

    items = [_item(claim="word " * 50), _item(family="F2", claim="short")]
    text, ids, tokens = render_packet(items, 1, 70, count)
    assert tokens <= 70 and ids == [items[1].evidence_id]
    text, ids, _ = render_packet([], 2, 70, count)
    assert text == NEUTRAL_PACKET.format(checkpoint=2) and ids == []


def test_feature_columns_never_name_outcome_plane_quantities():
    for name in ITEM_COLUMNS + STATE_COLUMNS + LOGPROB_COLUMNS:
        assert not any(word in name for word in OUTCOME_PLANE_WORDS), name
    assert set(EvidenceItem.model_fields).isdisjoint({"bug_discriminative", "aev", "grade"})


def test_statistics():
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(10, 0) == pytest.approx(0.001953125)
    adjusted = holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adjusted["a"] == pytest.approx(0.03)
    assert adjusted["c"] == pytest.approx(0.06) and adjusted["b"] == pytest.approx(0.06)
    assert mcnemar_pairs_needed(0.15, 0.05) == pytest.approx(468, abs=3)
    result = paired_contrast([1, 1, 0, 1], [0, 1, 0, 0], ["r1", "r1", "r2", "r3"], n_boot=200)
    assert result["only_a"] == 2 and result["only_b"] == 0
    assert result["difference"] == pytest.approx(0.5)


def test_truncate_middle_keeps_ends():
    text = "a" * 100 + "b" * 100
    out = truncate_middle(text, 80)
    assert out.startswith("a") and out.endswith("b") and len(out) <= 80


def test_config_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        StudyConfig.model_validate({"study_id": "x", "nonsense": 1})
    cfg = StudyConfig.model_validate({"study_id": "x", "validate": {"n_checkpoints": 3}})
    assert cfg.validate_.n_checkpoints == 3 and len(cfg.digest()) == 64
    assert np.isclose(cfg.split.train + cfg.split.dev + cfg.split.confirm, 1.0)


def test_swe_rebench_v2_rows(repo_rows):
    cfg = DataConfig(source="swe_rebench_v2", created_after="2025-05-01")
    row = dict(repo_rows[0], language="python", created_at="2025-06-02 10:00:00")
    row.pop("docker_image", None)
    row["image_name"] = "docker.io/swerebenchv2/x-y:1-abc"
    assert eligibility(row, cfg, set()) is None
    assert task_from_row(row, "swe_rebench_v2").image == "docker.io/swerebenchv2/x-y:1-abc"
    assert eligibility(dict(row, language="go"), cfg, set()) == "not_python"
    millis = dict(row, created_at=1746057600000)  # 2025-05-01 00:00 UTC as Unix milliseconds
    assert eligibility(millis, cfg, set()) is None
    assert task_from_row(millis, "swe_rebench_v2").created_at == "2025-05-01 00:00:00"
    assert eligibility(dict(row, created_at="2025-04-30 23:59:59"), cfg, set()) == "before_cutoff"


def test_sandbox_workdir_follows_config():
    from veritas.config import SandboxConfig
    from veritas.sandbox import LocalSandbox, SandboxError

    class Probe(LocalSandbox):
        def __init__(self, cfg):  # no workspace: relpath only
            super(LocalSandbox, self).__init__(cfg)

    sandbox = Probe(SandboxConfig(kind="local", workdir="/wtforms"))
    assert sandbox.relpath("/wtforms/a/b.py") == "a/b.py"
    with pytest.raises(SandboxError):
        sandbox.relpath("/testbed/a.py")
    assert Probe(SandboxConfig(kind="local", workdir=None)).workdir == "/testbed"


def test_fetch_helpers():
    from datetime import datetime

    from veritas.datafetch import _json_default, _split_ref

    assert _split_ref("org/data@abc123") == ("org/data", "abc123")
    with pytest.raises(SystemExit):
        _split_ref("org/data")
    assert _json_default(datetime(2025, 5, 1, 12, 0)) == "2025-05-01 12:00:00"


def test_parse_qwen3_coder_xml_tool_calls():
    text = (
        "I will fix it.\n<tool_call>\n<function=str_replace_editor>\n"
        "<parameter=command>\nstr_replace\n</parameter>\n<parameter=path>\ncalc.py\n</parameter>\n"
        "<parameter=old_str>\n    return a - b\n\n</parameter>\n"
        "<parameter=new_str>\n    return a + b\n</parameter>\n</function>\n</tool_call>"
    )
    call = parse_tool_calls(text).calls[0]
    assert call.name == "str_replace_editor"
    assert call.arguments == {"command": "str_replace", "path": "calc.py",
                              "old_str": "    return a - b\n", "new_str": "    return a + b"}
    insert = ("<tool_call>\n<function=str_replace_editor>\n<parameter=command>\ninsert\n"
              "</parameter>\n<parameter=insert_line>\n3\n</parameter>\n</function>\n</tool_call>")
    assert parse_tool_calls(insert).calls[0].arguments["insert_line"] == 3
    assert parse_tool_calls("<tool_call>\n<function=rm>\n</function>\n</tool_call>").errors
