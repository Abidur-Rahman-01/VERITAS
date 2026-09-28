import hashlib
import os
import shutil
import stat
import tarfile
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from .io import digest, write_json


def tree_hash(root):
    root = Path(root)
    h = hashlib.sha256()
    h.update(b"ROOT\0" + str(stat.S_IMODE(root.stat().st_mode)).encode() + b"\0")
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlinks are not supported in the transactional workspace: {path}")
        relative = path.relative_to(root).as_posix().encode()
        if path.is_dir():
            h.update(
                b"D\0" + relative + b"\0" + str(stat.S_IMODE(path.stat().st_mode)).encode() + b"\0"
            )
        elif path.is_file():
            h.update(
                b"F\0" + relative + b"\0" + str(stat.S_IMODE(path.stat().st_mode)).encode() + b"\0"
            )
            contents = hashlib.sha256()
            with path.open("rb") as f:
                for block in iter(lambda: f.read(1024 * 1024), b""):
                    contents.update(block)
            # Fixed-size content digests prevent ambiguous concatenation across files.
            h.update(contents.digest())
        else:
            raise ValueError("Special files are not supported")
    return h.hexdigest()


class Checkpoint:
    def __init__(self, workspace, directory):
        self.workspace, self.directory = Path(workspace).resolve(), Path(directory).resolve()
        if self.directory == self.workspace or self.workspace in self.directory.parents:
            raise ValueError("Checkpoint must live outside the workspace")
        self.before = tree_hash(self.workspace)
        shutil.copytree(self.workspace, self.directory)

    def restore(self):
        shutil.rmtree(self.workspace)
        shutil.copytree(self.directory, self.workspace)
        restored = tree_hash(self.workspace)
        if restored != self.before:
            raise RuntimeError("Checkpoint restoration hash mismatch")
        return restored

    def close(self):
        shutil.rmtree(self.directory, ignore_errors=True)


CONTINUATION_FIELDS = {
    "conversation",
    "pending_action",
    "step_counter",
    "budget",
    "trigger_state",
    "planner_state",
    "model_config_hashes",
    "random_state",
}

BRANCH_STATUSES = {"created", "running", "completed", "failed", "interrupted"}


def _require_outside_workspace(workspace, directory):
    workspace, directory = Path(workspace).resolve(), Path(directory).resolve()
    if directory == workspace or workspace in directory.parents:
        raise ValueError("Continuation checkpoint must live outside the workspace")
    return workspace, directory


def _validate_budget(budget):
    if not isinstance(budget, dict):
        raise ValueError("Continuation budget must be a JSON object")
    for key in ("unit", "total", "spent", "remaining"):
        if key not in budget:
            raise ValueError(f"Continuation budget missing: {key}")
    total, spent, remaining = (Decimal(str(budget[key])) for key in ("total", "spent", "remaining"))
    if total < 0 or spent < 0 or remaining < 0 or spent + remaining != total:
        raise ValueError("Continuation budget totals are inconsistent")


def _validate_continuation_state(state):
    if not isinstance(state, dict):
        raise ValueError("Continuation state must be a JSON object")
    missing = CONTINUATION_FIELDS - set(state)
    if missing:
        raise ValueError(f"Continuation state missing fields: {sorted(missing)}")
    if state.get("unsupported_state"):
        raise ValueError(f"Unsupported continuation state: {state['unsupported_state']}")
    if not isinstance(state["conversation"], list):
        raise ValueError("Continuation conversation must be a list")
    if not isinstance(state["step_counter"], int) or state["step_counter"] < 0:
        raise ValueError("Continuation step counter must be a non-negative integer")
    _validate_budget(state["budget"])
    for key in ("trigger_state", "planner_state", "model_config_hashes"):
        if not isinstance(state[key], dict):
            raise ValueError(f"Continuation {key} must be a JSON object")
    if not state["model_config_hashes"]:
        raise ValueError("Continuation must include model/config hashes")
    return deepcopy(state)


def create_continuation_checkpoint(workspace, directory, continuation_state):
    """Persist a complete pre-branch continuation state and workspace atomically.

    The saved state is JSON-only by design. External processes, network handles,
    mounted services, and other side effects must be represented by
    ``unsupported_state`` and are refused rather than silently dropped.
    """
    workspace, directory = _require_outside_workspace(workspace, directory)
    if directory.exists():
        raise ValueError("Continuation checkpoint already exists")
    state = _validate_continuation_state(continuation_state)
    before = tree_hash(workspace)
    partial = directory.with_name(f".{directory.name}.partial")
    if partial.exists():
        raise ValueError("Partial continuation checkpoint already exists")
    try:
        partial.mkdir(parents=True)
        shutil.copytree(workspace, partial / "workspace")
        copied = tree_hash(partial / "workspace")
        if copied != before:
            raise RuntimeError("Continuation checkpoint copy hash mismatch")
        manifest = {
            "schema_version": 1,
            "status": "ready",
            "checkpoint_id": digest({"workspace_hash": before, "state": state}),
            "workspace_hash": before,
            "continuation_state": state,
            "state_sha256": digest(state),
        }
        write_json(partial / "manifest.json", manifest)
        partial.rename(directory)
        return manifest
    except Exception:
        shutil.rmtree(partial, ignore_errors=True)
        raise


def verify_continuation_checkpoint(directory, expected_model_config_hashes=None):
    directory = Path(directory)
    manifest_path = directory / "manifest.json"
    workspace = directory / "workspace"
    if not manifest_path.exists() or not workspace.is_dir():
        raise ValueError("Continuation checkpoint is incomplete")
    import json

    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != 1 or manifest.get("status") != "ready":
        raise ValueError("Unsupported continuation checkpoint")
    state = _validate_continuation_state(manifest.get("continuation_state"))
    if digest(state) != manifest.get("state_sha256"):
        raise ValueError("Continuation state integrity failure")
    if tree_hash(workspace) != manifest.get("workspace_hash"):
        raise ValueError("Continuation workspace integrity failure")
    expected = expected_model_config_hashes
    if expected is not None and state["model_config_hashes"] != expected:
        raise ValueError("Continuation model/config hashes do not match")
    if digest({"workspace_hash": manifest["workspace_hash"], "state": state}) != manifest.get(
        "checkpoint_id"
    ):
        raise ValueError("Continuation checkpoint identity mismatch")
    return manifest


def restore_continuation_checkpoint(directory, workspace, expected_model_config_hashes=None):
    manifest = verify_continuation_checkpoint(directory, expected_model_config_hashes)
    workspace = Path(workspace)
    if workspace.exists():
        raise ValueError("Restore destination already exists")
    shutil.copytree(Path(directory) / "workspace", workspace)
    restored = tree_hash(workspace)
    if restored != manifest["workspace_hash"]:
        raise RuntimeError("Continuation restore hash mismatch")
    return restored


def fork_continuation_checkpoint(
    checkpoint, directory, branch_id, branch_metadata=None, expected_model_config_hashes=None
):
    manifest = verify_continuation_checkpoint(checkpoint, expected_model_config_hashes)
    directory = Path(directory)
    if directory.exists():
        raise ValueError("Branch directory already exists")
    if not branch_id or "/" in branch_id or "\\" in branch_id or branch_id in {".", ".."}:
        raise ValueError("Branch ID must be a simple non-empty name")
    partial = directory.with_name(f".{directory.name}.partial")
    if partial.exists():
        raise ValueError("Partial branch directory already exists")
    try:
        partial.mkdir(parents=True)
        shutil.copytree(Path(checkpoint) / "workspace", partial / "workspace")
        copied = tree_hash(partial / "workspace")
        if copied != manifest["workspace_hash"]:
            raise RuntimeError("Branch copy hash mismatch")
        state = deepcopy(manifest["continuation_state"])
        branch = {
            "schema_version": 1,
            "branch_id": branch_id,
            "parent_checkpoint_id": manifest["checkpoint_id"],
            "parent_workspace_hash": manifest["workspace_hash"],
            "workspace_hash": copied,
            "status": "created",
            "continuation_state": state,
            "branch_metadata": branch_metadata or {},
            "transitions": [{"status": "created", "reason": "forked_from_checkpoint"}],
            "charges": [],
            "logical_budget_spent": state["budget"]["spent"],
            "logical_budget_remaining": state["budget"]["remaining"],
            "prefix_reuse": "physical_prefix_reused_logical_cost_preserved",
        }
        write_json(partial / "branch.json", branch)
        partial.rename(directory)
        return branch
    except Exception:
        shutil.rmtree(partial, ignore_errors=True)
        raise


def verify_branch(directory):
    import json

    branch_path = Path(directory) / "branch.json"
    if not branch_path.exists():
        raise ValueError("Branch manifest is missing")
    branch = json.loads(branch_path.read_text())
    if branch.get("schema_version") != 1 or branch.get("status") not in BRANCH_STATUSES:
        raise ValueError("Unsupported branch manifest")
    _validate_continuation_state(branch.get("continuation_state"))
    if tree_hash(Path(directory) / "workspace") != branch.get("workspace_hash"):
        raise ValueError("Branch workspace integrity failure")
    return branch


def transition_branch(directory, status, reason, failure=None):
    if status not in BRANCH_STATUSES:
        raise ValueError("Unknown branch status")
    branch = verify_branch(directory)
    if branch["status"] in {"completed", "failed"} and branch["status"] != status:
        raise ValueError("Terminal branch status cannot transition")
    entry = {"status": status, "reason": reason}
    if failure is not None:
        entry["failure"] = failure
    branch["status"] = status
    branch["transitions"].append(entry)
    write_json(Path(directory) / "branch.json", branch)
    return branch


def charge_branch(directory, event_id, cost):
    if not event_id:
        raise ValueError("Charge event ID is required")
    cost = Decimal(str(cost))
    if cost <= 0:
        raise ValueError("Charge cost must be positive")
    branch = verify_branch(directory)
    for charge in branch["charges"]:
        if charge["event_id"] == event_id:
            return branch
    budget = branch["continuation_state"]["budget"]
    total = Decimal(str(budget["total"]))
    spent = Decimal(str(budget["spent"])) + sum(
        Decimal(str(charge["cost"])) for charge in branch["charges"]
    )
    if spent + cost > total:
        raise ValueError("Branch logical budget exhausted")
    branch["charges"].append({"event_id": event_id, "cost": float(cost)})
    branch["logical_budget_spent"] = float(spent + cost)
    branch["logical_budget_remaining"] = float(total - spent - cost)
    write_json(Path(directory) / "branch.json", branch)
    return branch


def safe_extract(archive, destination, max_bytes=256 * 1024 * 1024):
    """Never let a container-controlled archive follow links or escape its destination."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    total = 0
    with tarfile.open(archive, "r:*") as tar:
        for member in tar:
            path = destination / member.name
            if path.resolve() != destination and destination not in path.resolve().parents:
                raise ValueError("Container returned an escaping archive path")
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise ValueError("Container returned a link or special file")
            total += member.size
            if total > max_bytes:
                raise ValueError("Workspace exceeds the 256 MiB export limit")
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as src, path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                os.chmod(path, member.mode & 0o777)
