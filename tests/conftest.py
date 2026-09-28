"""Small deterministic software-test fixtures, never used as experimental datasets."""

import pytest

from veritas.contracts import contract
from veritas.schema import Proposal, StepRecord, Verification


@pytest.fixture
def step():
    def make(index=0, **updates):
        action = contract(Proposal(tool="final_answer", args={"answer": "2"}))
        values = dict(
            event_id=f"event-{index}",
            task_id=f"task-{index}",
            group_id=f"task-{index}",
            source="unit-test-only",
            run_id="run",
            model="stub",
            step_id=index,
            split="test",
            context="A unit-test context",
            action=action,
            raw_logit=2.0 if index % 2 else -2.0,
            p_error=0.8 if index % 2 else 0.2,
            impact=0.8,
            detection_rate=0.9,
            false_positive_rate=0.1,
            residual_loss=0.05,
            decision="skip",
            verification=Verification(
                verdict="FAIL" if index % 2 else "PASS", reason="test assertion"
            ),
            audit_only=True,
            verifier_cost=0.02,
            false_alarm_cost=0.1,
            error_label=index % 2,
            label_scope="semantic",
            label_source="unit-test assertion",
            state_before="before",
            restored_hash="before",
        )
        values.update(updates)
        return StepRecord(**values).model_dump(mode="json")

    return make


@pytest.fixture
def awareness_setup(tmp_path, monkeypatch):
    """Build local frozen studies and IO doubles; never contact Docker or a model."""
    import difflib
    import json
    from pathlib import Path
    from types import SimpleNamespace

    import veritas.awareness as planner
    import veritas.awareness_grading as grading
    from veritas.awareness import ActorSpec, GraderSpec, PhaseLimits, StudyProtocol
    from veritas.awareness_runtime import Services
    from veritas.config import ModelConfig
    from veritas.io import digest, file_hash, write_json
    from veritas.schema import Task, Usage

    actor = ActorSpec(id="actor", family="unit-actor", revision="fixture-revision",
                      model=ModelConfig(name="actor", max_tokens=20))
    reviewer = ActorSpec(id="reviewer", family="unit-reviewer", revision="fixture-revision",
                         model=ModelConfig(name="reviewer", max_tokens=20))
    tasks = [Task(task_id=f"unit-{i}", group_id=f"group-{i}", source="unit",
        source_revision="fixture", source_split="train", kind="swe", prompt="Fix value.py",
        official_holdout=False, repo=f"fixture/repo-{i}", base_commit="a"*40,
        private={"instance_id": f"fixture__repo-{i}", "patch": "PRIVATE_GOLD",
                 "test_patch": "PRIVATE_TEST", "repo": f"fixture/repo-{i}"}) for i in range(4)]
    prepared = tmp_path / "prepared"
    write_json(prepared / "manifest.json", {"fixture": True})
    splits = {"version": 1, "source": "unit", "seed": 42,
        "repositories": {name: [tasks[i].repo] for i, name in enumerate(planner.PARTITIONS)},
        "parent_manifest_sha256": file_hash(prepared / "manifest.json")}
    splits["split_id"] = digest(splits)
    write_json(tmp_path / "splits.json", splits)
    spec = StudyProtocol(name="fixture", tasks=str(prepared), splits=str(tmp_path / "splits.json"),
        source="unit", actors=[actor], reviewer=reviewer,
        images={t.private["instance_id"]: "fixture-image" for t in tasks},
        grader=GraderSpec(identity="fixture-harness"), draft=PhaseLimits(steps=3, completion_tokens=60),
        revision=PhaseLimits(steps=3, completion_tokens=60), bootstrap_samples=100,
        shadow_sample_probability=1)
    monkeypatch.setattr(planner, "load_tasks", lambda *args, **kwargs: [(t, {}) for t in tasks])
    monkeypatch.setattr(grading, "harness_fingerprint", lambda _: {"sha256": "f"*64,
                                                                "files": {}, "origin": None})
    requests, workspaces = [], []

    class Model:
        def __init__(self, config):
            self.config = config

        def complete(self, system, user, *, max_tokens, timeout_seconds):
            requests.append({"model": self.config.name, "system": system, "user": user,
                             "cap": max_tokens, "timeout": timeout_seconds})
            if self.config.name == "reviewer":
                return json.dumps({"verdict": "PASS", "findings": []}), Usage(
                    prompt_tokens=4, completion_tokens=4)
            value = json.loads(user)
            if "question" in value:
                return '{"stated_probability": null}', Usage(prompt_tokens=4, completion_tokens=4)
            history = value["recent_history"]
            if value["steps_remaining"] == 3:
                action = {"tool": "write_file", "args": {"path": "value.py", "content":
                    "value = 1\n" if value["phase"] == "draft" else "value = 2\n"}}
            else:
                action = {"tool": "final_answer", "args": {"answer": "Done"}}
            assert isinstance(history, list)
            return json.dumps(action), Usage(prompt_tokens=4, completion_tokens=4)

        def close(self):
            pass

    class Sandbox:
        def __init__(self, workspace, config):
            self.workspace = Path(workspace)
            self.workspace.mkdir(parents=True)
            self.config = config
            workspaces.append(self.workspace)

        def preflight(self):
            return "sha256:" + "b"*64

        def execute(self, action):
            if action.proposal.tool == "write_file":
                (self.workspace / action.proposal.args["path"]).write_text(action.proposal.args["content"])
            return {"exit_code": 0, "output": "done"}

    def initialize(image, work, commit, platform):
        (Path(work) / "value.py").write_text("value = 0\n")

    def patch(before, after):
        old = (Path(before) / "value.py").read_text().splitlines(keepends=True)
        new = (Path(after) / "value.py").read_text().splitlines(keepends=True)
        return "".join(difflib.unified_diff(old, new, fromfile="a/value.py", tofile="b/value.py"))

    counter = 0

    def create(**updates):
        nonlocal counter
        counter += 1
        protocol = StudyProtocol.model_validate({**spec.model_dump(mode="json"), **updates})
        config = tmp_path / f"study-{counter}.json"
        write_json(config, protocol.model_dump(mode="json"))
        root = tmp_path / f"study-{counter}"
        planner.create_study(config, root)
        return root

    return SimpleNamespace(spec=spec, tasks=tasks, splits=splits, create=create,
        requests=requests, workspaces=workspaces, model=Model, sandbox=Sandbox,
        services=Services(Model, Sandbox, initialize, patch))
