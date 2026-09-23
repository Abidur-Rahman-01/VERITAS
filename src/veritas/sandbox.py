import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from .config import SandboxConfig
from .io import canonical
from .schema import ActionContract
from .state import safe_extract, tree_hash


def command(argv, timeout=120, input=None):
    result = subprocess.run(
        argv,
        input=input,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"Command failed ({argv[0]}): {result.stderr.decode(errors='replace')[-2000:]}"
        )
    return result.stdout


class DockerSandbox:
    """Disposable containers, no host bind mounts, no network or external side effects.

    Only /testbed is durable; all other container state is discarded after each action.
    File mutations return through a validated tar archive, never a shared host directory.
    """

    def __init__(self, workspace, config: SandboxConfig):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.config = config

    def preflight(self):
        command(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=20)
        # Never silently pull unpinned / unexpected images during inference.
        return (
            command(
                ["docker", "image", "inspect", self.config.image, "--format", "{{.Id}}"], timeout=20
            )
            .decode()
            .strip()
        )

    def execute(self, action: ActionContract):
        if action.proposal.tool == "final_answer":
            return {"exit_code": 0, "output": action.proposal.args["answer"]}
        tree_hash(self.workspace)
        name = "veritas-" + uuid.uuid4().hex
        cfg = self.config
        setup = (
            "set -e; rm -rf /testbed; mv /veritas_workspace /testbed; cd /testbed; "
            "if [ -f /opt/miniconda3/bin/activate ]; then "
            ". /opt/miniconda3/bin/activate; conda activate testbed; fi; "
            "exec python /veritas_worker.py"
        )
        args = [
            "docker",
            "create",
            "--name",
            name,
            "-i",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "128",
            "--memory",
            cfg.memory,
            "--cpus",
            str(cfg.cpus),
            "--user",
            "0:0",
            "--ulimit",
            "fsize=268435456:268435456",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            f"VERITAS_TIMEOUT={max(1, cfg.timeout_seconds - 5)}",
            "--workdir",
            "/",
            "--entrypoint",
            "/bin/bash",
        ]
        if cfg.platform:
            args += ["--platform", cfg.platform]
        args += [cfg.image, "-c", setup]
        try:
            command(args)
            command(["docker", "cp", str(self.workspace), name + ":/veritas_workspace"])
            command(
                [
                    "docker",
                    "cp",
                    str(Path(__file__).with_name("worker.py")),
                    name + ":/veritas_worker.py",
                ]
            )
            try:
                raw = command(
                    ["docker", "start", "-a", "-i", name],
                    timeout=cfg.timeout_seconds,
                    input=canonical(action.proposal.model_dump(mode="json")),
                )
            except subprocess.TimeoutExpired:
                command(["docker", "kill", name], timeout=20)
                return {"exit_code": 124, "output": "Sandbox timeout; workspace changes discarded"}
            try:
                result = json.loads(raw)
                if not isinstance(result, dict) or not isinstance(result.get("exit_code"), int):
                    raise ValueError("Invalid worker result")
                result["output"] = str(result.get("output", ""))[: cfg.max_output_chars]
            except (ValueError, TypeError) as e:
                raise RuntimeError("Container returned invalid worker output") from e
            with tempfile.TemporaryDirectory(prefix="veritas-export-") as tmp:
                archive = Path(tmp) / "workspace.tar"
                # Bound archive transfer rather than collecting arbitrary output in RAM.
                with archive.open("wb") as out:
                    process = subprocess.Popen(
                        ["docker", "cp", name + ":/testbed/.", "-"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                    )
                    size = 0
                    try:
                        while chunk := process.stdout.read(1024 * 1024):
                            size += len(chunk)
                            if size > 300 * 1024 * 1024:
                                raise ValueError("Workspace export exceeds 300 MiB")
                            out.write(chunk)
                        if process.wait(timeout=30):
                            raise RuntimeError("Failed to export sandbox workspace")
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.wait()
                extracted = Path(tmp) / "files"
                safe_extract(archive, extracted)
                tree_hash(extracted)
                shutil.rmtree(self.workspace)
                shutil.copytree(extracted, self.workspace)
            return result
        finally:
            subprocess.run(
                ["docker", "rm", "-f", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )


def initialize_swe_workspace(image, workspace, base_commit, platform=None):
    """Extract the baseline checkout from a prebuilt, trusted benchmark image.

    Initialization removes .git so future commits/gold patches cannot be read by the model.
    Requires local image preparation with the official harness before collection.
    """
    if len(base_commit) != 40 or any(c not in "0123456789abcdef" for c in base_commit):
        raise ValueError("Invalid base commit")
    name = "veritas-init-" + uuid.uuid4().hex
    argv = [
        "docker",
        "create",
        "--name",
        name,
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "0:0",
        "--entrypoint",
        "/bin/bash",
    ]
    if platform:
        argv += ["--platform", platform]
    script = (
        "set -e; cd /testbed; git -c safe.directory=/testbed reset --hard "
        + base_commit
        + "; rm -rf .git"
    )
    try:
        command(argv + [image, "-c", script])
        command(["docker", "start", "-a", name])
        # Docker start can return 0 when the container process fails: inspect its status.
        code = command(["docker", "inspect", "-f", "{{.State.ExitCode}}", name]).decode().strip()
        if code != "0":
            raise RuntimeError("Benchmark image initialization failed")
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "baseline.tar"
            with archive.open("wb") as f:
                subprocess.run(
                    ["docker", "cp", name + ":/testbed/.", "-"], stdout=f, check=True, timeout=120
                )
            safe_extract(archive, workspace)
        tree_hash(workspace)
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )


def make_patch(baseline, workspace):
    """Git runs only over a fresh, disposable host-side diff repository (no hooks)."""
    with tempfile.TemporaryDirectory(prefix="veritas-diff-") as tmp:
        root = Path(tmp) / "repo"
        shutil.copytree(baseline, root)
        tree_hash(workspace)
        env = {
            **os.environ,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "VERITAS",
            "GIT_AUTHOR_EMAIL": "veritas@localhost",
            "GIT_COMMITTER_NAME": "VERITAS",
            "GIT_COMMITTER_EMAIL": "veritas@localhost",
        }

        def git(*args):
            result = subprocess.run(
                ["git", "-c", "core.hooksPath=/dev/null", *args],
                cwd=root,
                env=env,
                check=True,
                capture_output=True,
            )
            return result.stdout

        git("init", "-q")
        git("add", "-f", ".")
        git("commit", "-qm", "baseline", "--allow-empty")
        for child in root.iterdir():
            if child.name != ".git":
                shutil.rmtree(child) if child.is_dir() else child.unlink()
        for child in Path(workspace).iterdir():
            if child.name == ".git":
                continue
            shutil.copytree(child, root / child.name) if child.is_dir() else shutil.copy2(
                child, root / child.name
            )
        git("add", "-f", ".")
        return git(
            "diff", "--cached", "--binary", "--no-ext-diff", "--no-textconv", "HEAD"
        ).decode()
