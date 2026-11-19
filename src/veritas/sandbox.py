"""Isolated repository workspaces.

``DockerSandbox`` runs one long-lived, network-less container per branch from the task's pinned
image. On start it removes the repository's git history and re-initialises a single ``base``
commit, so the agent cannot read future commits (hack-free evaluation). ``LocalSandbox`` offers
the same interface on a host directory and exists for tests and smoke runs.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .config import SandboxConfig

EXCLUDES = "__pycache__/\n*.pyc\n.pytest_cache/\n*.egg-info/\n.mypy_cache/\n"
RESET_GIT = (
    "rm -rf .git && git init -q && printf %s {excludes} > .git/info/exclude && git add -A && "
    "git -c user.email=veritas@localhost -c user.name=veritas commit -q --no-verify -m base"
)


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    output: str
    seconds: float

    @property
    def timed_out(self) -> bool:
        return self.exit_code in (124, 137)


class SandboxError(RuntimeError):
    pass


class Sandbox(ABC):
    def __init__(self, cfg: SandboxConfig):
        self.cfg = cfg
        self.sandbox_seconds = 0.0
        # Repository root inside the workspace. DockerSandbox replaces it with the image's
        # WORKDIR when ``cfg.workdir`` is None (SWE-rebench-V2 images use one per repository).
        self.workdir = cfg.workdir or "/testbed"

    # --- primitives -----------------------------------------------------------------------
    @abstractmethod
    def exec(self, command: str, timeout: int | None = None) -> ExecResult: ...

    @abstractmethod
    def read_file(self, path: str) -> str | None: ...

    @abstractmethod
    def write_file(self, path: str, content: str) -> None: ...

    @abstractmethod
    def snapshot(self) -> str: ...

    @abstractmethod
    def restore(self, snapshot_id: str) -> "Sandbox": ...

    @abstractmethod
    def drop_snapshot(self, snapshot_id: str) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @property
    @abstractmethod
    def environment_hash(self) -> str: ...

    # --- derived operations ---------------------------------------------------------------
    def relpath(self, path: str) -> str:
        """Normalise an agent-supplied path to a workspace-relative POSIX path, or raise."""
        p = PurePosixPath(path.strip())
        work = PurePosixPath(self.workdir)
        if p.is_absolute():
            try:
                p = p.relative_to(work)
            except ValueError as exc:
                raise SandboxError(f"path outside the repository: {path}") from exc
        if any(part == ".." for part in p.parts):
            raise SandboxError(f"path escapes the repository: {path}")
        text = str(p)
        return "" if text == "." else text

    def git(self, args: str, timeout: int = 120) -> ExecResult:
        return self.exec(f"git -c safe.directory='*' {args}", timeout=timeout)

    def diff(self) -> str:
        """Current patch against the base commit, including new and deleted files."""
        result = self.git("add -A && git -c safe.directory='*' diff --cached --binary HEAD")
        if result.exit_code != 0:
            raise SandboxError(f"git diff failed: {result.output[-500:]}")
        out = result.output
        return out if not out or out.endswith("\n") else out + "\n"

    def tree_hash(self) -> str:
        result = self.git("add -A && git -c safe.directory='*' write-tree")
        if result.exit_code != 0:
            raise SandboxError(f"git write-tree failed: {result.output[-500:]}")
        return result.output.strip().splitlines()[-1]

    def restore_tree(self, tree: str) -> None:
        """Reset the working tree to ``tree`` (a hash from ``tree_hash``): tracked content is
        restored and files created since are removed (ignored files are kept)."""
        result = self.git(f"read-tree -u --reset {tree} && git -c safe.directory='*' clean -fdq")
        if result.exit_code != 0:
            raise SandboxError(f"restore_tree failed: {result.output[-500:]}")

    def apply_patch(self, patch: str, name: str) -> ExecResult:
        if not patch.strip():
            return ExecResult(0, "empty patch", 0.0)
        target = f".veritas_{name}.patch"
        self.write_file(target, patch)
        result = self.git(f"apply --whitespace=nowarn {target} && rm -f {target}")
        if result.exit_code != 0:
            self.exec(f"rm -f {target}")
        return result

    def reset_files(self, paths: list[str]) -> None:
        if paths:
            quoted = " ".join(shlex.quote(p) for p in paths)
            self.git(f"checkout -q HEAD -- {quoted} 2>/dev/null; true")


class LocalSandbox(Sandbox):
    """Host-directory workspace (tests and smoke runs only; no isolation)."""

    def __init__(self, cfg: SandboxConfig, source_dir: str | Path, *, _root: Path | None = None):
        super().__init__(cfg)
        if _root is not None:
            self.root = _root
        else:
            self.root = Path(tempfile.mkdtemp(prefix="veritas-local-"))
            shutil.copytree(source_dir, self.root, dirs_exist_ok=True)
            result = self.exec(RESET_GIT.format(excludes=shlex.quote(EXCLUDES)))
            if result.exit_code != 0:
                raise SandboxError(f"git init failed: {result.output}")
        self._snapshots = Path(tempfile.gettempdir()) / "veritas-local-snapshots"

    def exec(self, command: str, timeout: int | None = None) -> ExecResult:
        limit = timeout or self.cfg.command_timeout_seconds
        start = time.monotonic()
        try:
            proc = subprocess.run(
                ["bash", "-c", command], cwd=self.root, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=limit, check=False,
            )
            code, out = proc.returncode, proc.stdout.decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired as exc:
            code = 124
            out = (exc.stdout or b"").decode("utf-8", errors="replace") + "\n[timed out]"
        seconds = time.monotonic() - start
        self.sandbox_seconds += seconds
        return ExecResult(code, out, seconds)

    def read_file(self, path: str) -> str | None:
        target = self.root / self.relpath(path)
        if not target.is_file():
            return None
        return target.read_text(encoding="utf-8", errors="replace")

    def write_file(self, path: str, content: str) -> None:
        target = self.root / self.relpath(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def snapshot(self) -> str:
        snap = "local-" + uuid.uuid4().hex
        shutil.copytree(self.root, self._snapshots / snap, symlinks=True)
        return snap

    def restore(self, snapshot_id: str) -> "LocalSandbox":
        root = Path(tempfile.mkdtemp(prefix="veritas-local-"))
        shutil.copytree(self._snapshots / snapshot_id, root, symlinks=True, dirs_exist_ok=True)
        return LocalSandbox(self.cfg, root, _root=root)

    def drop_snapshot(self, snapshot_id: str) -> None:
        shutil.rmtree(self._snapshots / snapshot_id, ignore_errors=True)

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    @property
    def environment_hash(self) -> str:
        return "local"


def _docker(args: list[str], timeout: int = 300, stdin: bytes | None = None) -> str:
    proc = subprocess.run(
        ["docker", *args], input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=timeout, check=False,
    )
    if proc.returncode != 0:
        raise SandboxError(
            f"docker {args[0]} failed: {proc.stderr.decode('utf-8', errors='replace')[-1500:]}"
        )
    return proc.stdout.decode("utf-8", errors="replace")


def _inspect(image: str) -> tuple[str, str]:
    """Image id and configured WORKDIR (a committed snapshot keeps its source's WORKDIR)."""
    out = _docker(["image", "inspect", image, "--format", "{{.Id}}|{{.Config.WorkingDir}}"], 60)
    image_id, _, workdir = out.strip().partition("|")
    return image_id, workdir


class DockerSandbox(Sandbox):
    def __init__(
        self, cfg: SandboxConfig, image: str, *, prepare: bool = True, env_hash: str | None = None
    ):
        super().__init__(cfg)
        self.image = image
        image_id, image_workdir = _inspect(image)
        # A restored snapshot keeps the environment hash of the task image it was derived from.
        self._image_id = env_hash or image_id
        if cfg.workdir is None:
            if not image_workdir:
                raise SandboxError(f"{image}: image has no WORKDIR; set sandbox.workdir")
            self.workdir = image_workdir
        self.name = "veritas-" + uuid.uuid4().hex[:16]
        args = [
            "run", "-d", "--name", self.name, "--network", cfg.network,
            "--memory", cfg.memory, "--cpus", str(cfg.cpus), "--pids-limit", "512",
            "--security-opt", "no-new-privileges", "--entrypoint", "/bin/bash",
        ]
        if cfg.platform:
            args += ["--platform", cfg.platform]
        _docker([*args, image, "-c", "sleep infinity"], 120)
        if prepare:
            result = self.exec(
                f"git -c safe.directory='*' status --porcelain >/dev/null 2>&1; "
                f"{RESET_GIT.format(excludes=shlex.quote(EXCLUDES))}",
                timeout=600,
            )
            if result.exit_code != 0:
                self.close()
                raise SandboxError(f"workspace preparation failed: {result.output[-1500:]}")

    def exec(self, command: str, timeout: int | None = None) -> ExecResult:
        limit = timeout or self.cfg.command_timeout_seconds
        script = f"{self.cfg.activate}; cd {shlex.quote(self.workdir)} && {command}"
        argv = ["docker", "exec", self.name, "timeout", "-s", "KILL", str(limit),
                "bash", "-c", script]
        start = time.monotonic()
        try:
            proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  timeout=limit + 30, check=False)
            code, out = proc.returncode, proc.stdout.decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            code, out = 124, "[timed out]"
        seconds = time.monotonic() - start
        self.sandbox_seconds += seconds
        return ExecResult(code, out, seconds)

    def read_file(self, path: str) -> str | None:
        rel = self.relpath(path)
        target = shlex.quote(f"{self.workdir}/{rel}")
        proc = subprocess.run(
            ["docker", "exec", self.name, "bash", "-c", f"test -f {target} && cat -- {target}"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60, check=False,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.decode("utf-8", errors="replace")

    def write_file(self, path: str, content: str) -> None:
        rel = self.relpath(path)
        target = f"{self.workdir}/{rel}"
        parent = str(PurePosixPath(target).parent)
        _docker(
            ["exec", "-i", self.name, "bash", "-c",
             f"mkdir -p {shlex.quote(parent)} && cat > {shlex.quote(target)}"],
            60, stdin=content.encode("utf-8"),
        )

    def snapshot(self) -> str:
        tag = f"veritas-snap:{uuid.uuid4().hex[:16]}"
        _docker(["commit", self.name, tag], 600)
        return tag

    def restore(self, snapshot_id: str) -> "DockerSandbox":
        return DockerSandbox(self.cfg, snapshot_id, prepare=False, env_hash=self._image_id)

    def drop_snapshot(self, snapshot_id: str) -> None:
        if not self.cfg.keep_snapshots:
            subprocess.run(["docker", "rmi", "-f", snapshot_id], capture_output=True, check=False)

    def close(self) -> None:
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True, check=False)

    @property
    def environment_hash(self) -> str:
        return self._image_id


def open_sandbox(cfg: SandboxConfig, image: str, local_source: str | None = None) -> Sandbox:
    if cfg.kind == "docker":
        return DockerSandbox(cfg, image)
    if not local_source:
        raise SandboxError("local sandbox requires a source directory")
    return LocalSandbox(cfg, local_source)


def restore_sandbox(cfg: SandboxConfig, image: str, snapshot_id: str) -> Sandbox:
    """Start a new workspace from a snapshot taken by ``Sandbox.snapshot``."""
    if cfg.kind == "docker":
        env_hash, _ = _inspect(image)
        return DockerSandbox(cfg, snapshot_id, prepare=False, env_hash=env_hash)
    source = Path(tempfile.gettempdir()) / "veritas-local-snapshots" / snapshot_id
    root = Path(tempfile.mkdtemp(prefix="veritas-local-"))
    shutil.copytree(source, root, symlinks=True, dirs_exist_ok=True)
    return LocalSandbox(cfg, root, _root=root)
