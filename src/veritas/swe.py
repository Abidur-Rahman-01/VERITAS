import inspect
import json
import shlex
import subprocess
import sys
from pathlib import Path

from .data import load_tasks
from .io import read_jsonl, write_json, write_jsonl


def image_map(
    tasks_dir,
    output,
    split="test",
    source="swe_verified",
    limit=None,
    namespace="swebench",
    arch="x86_64",
):
    """Ask the installed official harness for image names; never guess its naming convention."""
    from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
    from swebench.harness.test_spec.test_spec import TestSpec

    def key_for(row):
        # Image names need only metadata. Full make_test_spec may fetch requirements
        # from GitHub, which belongs to environment building, not image-map inspection.
        return TestSpec(
            instance_id=row["instance_id"],
            repo=row["repo"],
            version=row["version"],
            repo_script_list=[],
            eval_script_list=[],
            env_script_list=[],
            arch=arch,
            FAIL_TO_PASS=[],
            PASS_TO_PASS=[],
            language="py",
            docker_specs={},
            namespace=namespace or None,
        ).instance_image_key

    mapping, rows = {}, []
    for task, _ in load_tasks(tasks_dir, split, source, limit):
        if task.kind != "swe":
            raise ValueError("SWE image mapping requires repository tasks")
        row = dict(task.private)
        if task.source == "swe_rebench":
            known_image = row.get("docker_image") or row.get("image_name")
            if not known_image:
                try:
                    from swebench.harness.utils import _clean_install_config
                except ImportError as e:
                    raise ValueError(
                        "SWE-rebench needs the pinned upstream fork. Run scripts/setup_rebench.sh, then use .venv-rebench/bin/veritas with --namespace ''"
                    ) from e
                row = _clean_install_config(row)
                known_image = key_for(row)
            mapping[row["instance_id"]] = known_image
        else:
            try:
                MAP_REPO_VERSION_TO_SPECS[row["repo"]][row["version"]]
            except KeyError as e:
                raise ValueError(
                    f"Official harness has no environment recipe for {row['repo']} {row['version']}. This raw training item requires a repository-specific image; use a declared non-Verified swe_test research pool, swe_verified, or the SWE-rebench fork"
                ) from e
            mapping[row["instance_id"]] = key_for(row)
        rows.append(row)
    if not mapping:
        raise ValueError("No matching SWE tasks")
    write_json(output, mapping)
    dataset_path = Path(output).with_suffix(".tasks.jsonl")
    write_jsonl(dataset_path, rows)
    return {
        "images": len(mapping),
        "map": str(output),
        "harness_dataset": str(dataset_path),
        "next": "Pull public images with swe pull-images, or build with the official harness",
    }


def pull_images(mapping_path):
    mapping = json.loads(Path(mapping_path).read_text())
    for image in sorted(set(mapping.values())):
        subprocess.run(["docker", "pull", image], check=True)


def build_images(dataset, workers=2, arch="x86_64"):
    import docker
    from swebench.harness.docker_build import build_instance_images
    from swebench.harness.test_spec.test_spec import make_test_spec
    from swebench.harness.utils import load_swebench_dataset

    rows = load_swebench_dataset(str(dataset))
    kwargs = {"namespace": None}
    if "arch" in inspect.signature(make_test_spec).parameters:
        kwargs["arch"] = arch
    specs = [make_test_spec(row, **kwargs) for row in rows]
    for spec in specs:
        spec.arch = arch
    client = docker.from_env()
    try:
        build_kwargs = {"max_workers": workers, "tag": "latest"}
        if "env_image_tag" in inspect.signature(build_instance_images).parameters:
            build_kwargs["env_image_tag"] = "latest"
        successful, failed = build_instance_images(client, specs, **build_kwargs)
        if failed:
            raise RuntimeError(
                f"{len(failed)} environment builds failed; inspect logs/build_images"
            )
        return {"built_or_cached": len(successful), "failed": len(failed)}
    finally:
        client.close()


def evaluation_command(dataset, predictions, run_id, workers=2, namespace="swebench"):
    for row in read_jsonl(predictions):
        if not all(
            isinstance(row.get(key), str)
            for key in ("instance_id", "model_patch", "model_name_or_path")
        ):
            raise ValueError("Invalid official SWE-bench prediction format")
    return [
        sys.executable,
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        str(dataset),
        "--predictions_path",
        str(predictions),
        "--max_workers",
        str(workers),
        "--run_id",
        run_id,
        "--namespace",
        namespace or "none",
    ]


def evaluate_swe(dataset, predictions, run_id, workers=2, execute=False, namespace="swebench"):
    argv = evaluation_command(dataset, predictions, run_id, workers, namespace)
    if execute:
        subprocess.run(argv, check=True)
    return {"command": shlex.join(argv), "executed": execute}
