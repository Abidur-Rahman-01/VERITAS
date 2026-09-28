"""Create a checksummed, source-only index for a dependency research release."""

import json
import subprocess
from pathlib import Path

from .io import digest, file_hash, write_json

DENIED_PARTS = {".git", ".venv", ".venv-rebench", "data", "runs", "artifacts", ".env"}
ALLOWED_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".toml", ".lock", ".sh"}


def create_release_manifest(root, files, output):
    root = Path(root).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Release manifest already exists; use a new output path")
    entries = []
    seen = set()
    for value in files:
        supplied = Path(value)
        candidate = (root / supplied) if not supplied.is_absolute() else supplied
        if candidate.is_symlink():
            raise ValueError(f"Release input cannot be a symlink: {value}")
        path = candidate.resolve()
        try:
            relative = path.relative_to(root)
        except ValueError as exc:
            raise ValueError("Release inputs must remain inside the repository root") from exc
        if any(part in DENIED_PARTS or part.startswith(".env") for part in relative.parts):
            raise ValueError(f"Sensitive or generated path excluded from source release: {relative}")
        if not path.is_file():
            raise ValueError(f"Release input must be a regular file: {relative}")
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            raise ValueError(f"Unsupported release file type: {relative.suffix}")
        key = relative.as_posix()
        if key in seen:
            raise ValueError(f"Duplicate release input: {key}")
        seen.add(key)
        entries.append({"path": key, "sha256": file_hash(path), "bytes": path.stat().st_size})
    if not entries:
        raise ValueError("At least one release input is required")
    try:
        revision = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        revision = None
    manifest = {
        "schema_version": 1,
        "repository_revision": revision,
        "files": sorted(entries, key=lambda row: row["path"]),
        "scope": "source/configuration/documentation integrity index; no data or run artifacts included",
        "research_status": "software_artifacts_only_no_empirical_claims",
    }
    manifest["manifest_sha256"] = digest(manifest)
    write_json(output, manifest)
    return manifest


def verify_release_manifest(manifest_path, root):
    manifest_path = Path(manifest_path)
    root = Path(root).resolve()
    manifest = json.loads(manifest_path.read_text())
    expected = dict(manifest)
    checksum = expected.pop("manifest_sha256")
    if digest(expected) != checksum:
        raise ValueError("Release manifest checksum mismatch")
    mismatches = []
    for entry in manifest["files"]:
        candidate = root / entry["path"]
        if candidate.is_symlink():
            raise ValueError(f"Release input cannot be a symlink: {entry['path']}")
        path = candidate.resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("Manifest path escapes repository root") from exc
        if not path.is_file() or file_hash(path) != entry["sha256"]:
            mismatches.append(entry["path"])
    if mismatches:
        raise ValueError(f"Release inputs changed or missing: {mismatches[:5]}")
    return {"verified": True, "files": len(manifest["files"]), "manifest_sha256": checksum}
