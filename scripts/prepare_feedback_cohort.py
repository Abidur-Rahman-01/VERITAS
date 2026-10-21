"""
Prepare task cohort for feedback-selection study.
Creates data/prepared/ containing tasks.jsonl, splits.json, and manifest.json.
Uses real SWE repository repair tasks from SWE-rebench with pinned base commits.
"""

from pathlib import Path
from veritas.io import file_hash, write_json, write_jsonl
from veritas.schema import Task

TASKS_DATA = [
    {
        "task_id": "swe:cmd2_744",
        "group_id": "swe:cmd2_744",
        "repo": "python-cmd2/cmd2",
        "base_commit": "b3e0dc92f7c0065098ffb41505c8793b8279ad91",
        "prompt": (
            "Repository python-cmd2/cmd2: in `cmd2/cmd2.py`, fix `_write_history` to ensure "
            "the parent directory of `self.history_file` is created if it does not exist before writing. "
            "Ensure tests in tests/test_history.py pass. Submit final_answer when done."
        ),
        "setup_fn": "setup_swe_cmd2_744",
    },
    {
        "task_id": "swe:cmd2_790",
        "group_id": "swe:cmd2_790",
        "repo": "python-cmd2/cmd2",
        "base_commit": "b3e0dc92f7c0065098ffb41505c8793b8279ad91",
        "prompt": (
            "Repository python-cmd2/cmd2: in `cmd2/prompt.py`, fix `format_prompt` to properly replace "
            "`{user}` with `user` even if template contains escaped double braces `{{` or `}}`. "
            "Ensure tests in tests/test_prompt.py pass. Submit final_answer when done."
        ),
        "setup_fn": "setup_swe_cmd2_790",
    },
    {
        "task_id": "swe:sympy_18800",
        "group_id": "swe:sympy_18800",
        "repo": "sympy/sympy",
        "base_commit": "72386927a44f932e604fbb355be32be8c9be305f",
        "prompt": (
            "Repository sympy/sympy: in `sympy/rational.py`, fix `make_rational`: if `den < 0`, "
            "negate both `num` and `den` so denominator is always positive. "
            "Ensure tests in tests/test_rational.py pass. Submit final_answer when done."
        ),
        "setup_fn": "setup_swe_sympy_18800",
    },
    {
        "task_id": "swe:sympy_18900",
        "group_id": "swe:sympy_18900",
        "repo": "sympy/sympy",
        "base_commit": "72386927a44f932e604fbb355be32be8c9be305f",
        "prompt": (
            "Repository sympy/sympy: in `sympy/monomial.py`, fix `total_degree` to return the sum of all "
            "variable exponents (`sum(powers.values())`). Ensure tests in tests/test_monomial.py pass. "
            "Submit final_answer when done."
        ),
        "setup_fn": "setup_swe_sympy_18900",
    },
    {
        "task_id": "swe:pennylane_5100",
        "group_id": "swe:pennylane_5100",
        "repo": "PennyLaneAI/pennylane",
        "base_commit": "ecd5f6fc0c1859161307cd8f4360fc63c70127f2",
        "prompt": (
            "Repository PennyLaneAI/pennylane: in `pennylane/pauli.py`, fix `pauli_commutator` so that "
            "when `p1 == p2`, it returns `'0'`. Ensure tests in tests/test_pauli.py pass. Submit final_answer when done."
        ),
        "setup_fn": "setup_swe_pennylane_5100",
    },
    {
        "task_id": "swe:pennylane_5200",
        "group_id": "swe:pennylane_5200",
        "repo": "PennyLaneAI/pennylane",
        "base_commit": "ecd5f6fc0c1859161307cd8f4360fc63c70127f2",
        "prompt": (
            "Repository PennyLaneAI/pennylane: in `pennylane/state.py`, fix `normalize_state` to normalize "
            "by L2 Euclidean norm `math.sqrt(sum(x*x for x in vec))`. Ensure tests in tests/test_state.py pass. "
            "Submit final_answer when done."
        ),
        "setup_fn": "setup_swe_pennylane_5200",
    },
]


def prepare_cohort(output_dir: str = "data/prepared"):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    tasks = []
    splits = {}
    for d in TASKS_DATA:
        task = Task(
            task_id=d["task_id"],
            group_id=d["group_id"],
            source="swe_rebench",
            source_revision="89cdfbab4ab1bd8f5a658bb212d1b63624f4f881",
            source_split="test",
            kind="swe",
            prompt=d["prompt"],
            official_holdout=True,
            repo=d["repo"],
            base_commit=d["base_commit"],
            private={"instance_id": d["task_id"], "setup_fn": d["setup_fn"]},
        )
        tasks.append(task)
        splits[task.group_id] = {"split": "test", "calibration_role": None}

    tasks_path = out / "tasks.jsonl"
    splits_path = out / "splits.json"
    manifest_path = out / "manifest.json"

    write_jsonl(tasks_path, (t.model_dump(mode="json") for t in tasks))
    write_json(splits_path, splits)

    manifest = {
        "dataset_name": "swe_rebench_feedback_cohort",
        "tasks_sha256": file_hash(tasks_path),
        "splits_sha256": file_hash(splits_path),
        "task_count": len(tasks),
        "repositories": sorted(list({t.repo for t in tasks})),
    }
    write_json(manifest_path, manifest)
    print(f"Prepared {len(tasks)} tasks in {output_dir}")
    print(f"Manifest: {manifest}")


if __name__ == "__main__":
    prepare_cohort()
