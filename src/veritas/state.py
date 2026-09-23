import hashlib
import os
import shutil
import stat
import tarfile
from pathlib import Path


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
