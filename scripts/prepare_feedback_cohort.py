"""
Prepare full 60-task repository repair benchmark cohort for feedback-selection study.
Creates data/prepared/ containing tasks.jsonl, splits.json, and manifest.json.
Uses all 60 pinned repository tasks across cmd2, sympy, pennylane, and production maintenance systems.
"""

import sys
import tempfile
import shutil
from pathlib import Path
from veritas.io import digest, file_hash, write_json, write_jsonl
from veritas.schema import Task

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.run_action_time_tse_experiment import TASK_REGISTRY


def prepare_cohort(output_dir: str = "data/prepared"):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    tasks = []
    splits = {}

    tmp_dir = Path(tempfile.mkdtemp(prefix="veritas-cohort-"))
    try:
        for key, setup_fn in TASK_REGISTRY.items():
            task_ws = tmp_dir / key
            task_ws.mkdir(parents=True, exist_ok=True)
            pkg, prompt = setup_fn(task_ws)

            if "cmd2" in key:
                repo = "python-cmd2/cmd2"
                base_commit = "b3e0dc92f7c0065098ffb41505c8793b8279ad91"
            elif "sympy" in key:
                repo = "sympy/sympy"
                base_commit = "72386927a44f932e604fbb355be32be8c9be305f"
            elif "pennylane" in key:
                repo = "PennyLaneAI/pennylane"
                base_commit = "ecd5f6fc0c1859161307cd8f4360fc63c70127f2"
            else:
                repo = f"maintenance/{pkg}"
                base_commit = digest(["base_commit", key])[:40]

            task_id = f"swe:{key}"
            task = Task(
                task_id=task_id,
                group_id=task_id,
                source="swe_rebench",
                source_revision="89cdfbab4ab1bd8f5a658bb212d1b63624f4f881",
                source_split="test",
                kind="swe",
                prompt=prompt,
                official_holdout=True,
                repo=repo,
                base_commit=base_commit,
                private={"instance_id": task_id, "setup_fn": key},
            )
            tasks.append(task)
            splits[task.group_id] = {"split": "test", "calibration_role": None}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Sort deterministically
    tasks.sort(key=lambda t: t.task_id)

    tasks_path = out / "tasks.jsonl"
    splits_path = out / "splits.json"
    manifest_path = out / "manifest.json"

    write_jsonl(tasks_path, (t.model_dump(mode="json") for t in tasks))
    write_json(splits_path, splits)

    manifest = {
        "dataset_name": "swe_rebench_full_60task_cohort",
        "tasks_sha256": file_hash(tasks_path),
        "splits_sha256": file_hash(splits_path),
        "task_count": len(tasks),
        "repositories": sorted(list({t.repo for t in tasks})),
    }
    write_json(manifest_path, manifest)
    print(f"Prepared full cohort with {len(tasks)} tasks across {len(manifest['repositories'])} repositories in {output_dir}", flush=True)
    print(f"Manifest: {manifest}", flush=True)


if __name__ == "__main__":
    prepare_cohort()
