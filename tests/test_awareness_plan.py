import json
from collections import defaultdict

import pytest

from veritas.awareness import Assignment, DisclosurePolicy, StudyProtocol, plan_study, read_study
from veritas.awareness_store import StudyStore


def test_plan_balances_blocks_and_persists_slots(awareness_setup):
    f = awareness_setup
    selected, jobs = plan_study(f.spec, f.tasks, f.splits)
    assert len(selected) == 1
    assert jobs == plan_study(f.spec, f.tasks, f.splits)[1]
    blocks = defaultdict(list)
    for job in jobs:
        blocks[job.block_id].append(job)
        assert job.propensity == 0.25
        assert job.assignment_probability == 0.5
        assert job.disclosed_probability == (0.5 if job.disclosure_assigned else None)
        assert job.repository_id == selected[0].repo
        assert job.shadow_selected is not job.actual_assignment
    assert sorted(j.order for j in jobs) == list(range(len(jobs)))
    for block in blocks.values():
        assert {j.arm for j in block} == {"00", "10", "01", "11"}
        assert sorted(j.slot for j in block) == [0, 1, 2, 3]
    root = f.create()
    plan, _, _, stored = read_study(root, check_code=True)
    with StudyStore(root) as db:
        db.verify(plan["study_id"], stored)


def test_invalid_probability_and_inconsistent_assignment_rejected(awareness_setup):
    f = awareness_setup
    for probability in (0.1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            StudyProtocol.model_validate({**f.spec.model_dump(), "disclosure_probability": probability})
    job = plan_study(f.spec, f.tasks, f.splits)[1][0]
    with pytest.raises(ValueError):
        Assignment.model_validate({**job.model_dump(), "actual_assignment": not job.actual_assignment})
    with pytest.raises(ValueError):
        Assignment.model_validate({**job.model_dump(), "disclosure_assigned": False,
                                   "disclosed_probability": 0})
    assert "0%" in DisclosurePolicy(probability=0).render()


def test_aliases_cannot_cross_pools(awareness_setup):
    f = awareness_setup
    splits = json.loads(json.dumps(f.splits))
    splits["repositories"]["pilot"] = ["https://github.com/FIXTURE/REPO-0.git"]
    with pytest.raises(ValueError, match="aliases overlap"):
        plan_study(f.spec, f.tasks, splits)
    alias = f.tasks[1].model_copy(update={"group_id": f.tasks[0].group_id})
    with pytest.raises(ValueError, match="Task aliases cross"):
        plan_study(f.spec, [f.tasks[0], alias], f.splits)


def test_dose_is_development_only_and_has_truthful_assignment(awareness_setup):
    f = awareness_setup
    spec = StudyProtocol.model_validate({**f.spec.model_dump(), "design": "dose"})
    jobs = plan_study(spec, f.tasks, f.splits)[1]
    assert {j.disclosed_probability for j in jobs} == {0.1, 0.5, 0.9}
    assert all(j.disclosed_probability == j.assignment_probability for j in jobs)
    with pytest.raises(ValueError, match="Dose development"):
        StudyProtocol.model_validate({**spec.model_dump(), "partition": "pilot"})


def test_frozen_plan_tampering_is_detected(awareness_setup):
    root = awareness_setup.create()
    path = root / "assignments.jsonl"
    path.write_text(path.read_text().replace('"order":0', '"order":99'))
    with pytest.raises(ValueError, match="Frozen study file changed"):
        read_study(root)
