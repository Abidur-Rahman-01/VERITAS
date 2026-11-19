"""Download the task dataset and the actor's training-task ids from Hugging Face.

Everything is pinned to a dataset revision (a commit hash), so two machines that run
``veritas fetch-data`` with the same config get identical files. Parquet is read column-wise over
HTTP range requests, so the exclusion lists cost a few MB even when the training datasets hold
gigabytes of trajectories. Needs the ``data`` extra (huggingface_hub, pyarrow).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from .config import DataConfig
from .util import atomic_write_text


def _filesystem():
    try:
        from huggingface_hub import HfFileSystem
    except ImportError as exc:  # pragma: no cover - depends on the installed extras
        raise SystemExit("fetch-data needs the data extra: uv sync --extra data") from exc
    return HfFileSystem()


def _parquet_files(fs, repo: str, revision: str, split: str | None) -> list[str]:
    pattern = f"{split}-*.parquet" if split else "*.parquet"
    files = sorted(fs.glob(f"datasets/{repo}@{revision}/data/{pattern}"))
    if not files:
        raise SystemExit(f"no parquet files for {repo}@{revision} split={split}")
    return files


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    raise TypeError(f"cannot serialise {type(value).__name__}")


def _split_ref(ref: str) -> tuple[str, str]:
    repo, sep, revision = ref.partition("@")
    if not sep or not revision:
        raise SystemExit(f"exclude_hf_datasets entry must be 'repo@revision': {ref}")
    return repo, revision


def fetch(cfg: DataConfig, force: bool = False) -> dict:
    import pyarrow.parquet as pq

    fs = _filesystem()
    out = Path(cfg.dataset_path)
    manifest_path = out.with_suffix(".manifest.json")
    summary: dict = {}
    if out.exists() and manifest_path.exists() and not force:
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("repo") == cfg.hf_dataset and manifest.get("revision") == cfg.hf_revision:
            summary["dataset"] = {"skipped": "already present", **manifest}
        else:
            raise SystemExit(f"{out} holds {manifest.get('repo')}@{manifest.get('revision')}; "
                             "use another dataset_path or --force")
    if "dataset" not in summary:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".jsonl.part")
        digest, rows = hashlib.sha256(), 0
        with tmp.open("w", encoding="utf-8") as handle:
            for name in _parquet_files(fs, cfg.hf_dataset, cfg.hf_revision, cfg.hf_split):
                parquet = pq.ParquetFile(name, filesystem=fs)
                for batch in parquet.iter_batches(batch_size=256):
                    for row in batch.to_pylist():
                        line = json.dumps(row, ensure_ascii=False, default=_json_default) + "\n"
                        handle.write(line)
                        digest.update(line.encode("utf-8"))
                        rows += 1
        tmp.replace(out)
        manifest = {"repo": cfg.hf_dataset, "revision": cfg.hf_revision, "split": cfg.hf_split,
                    "rows": rows, "sha256": digest.hexdigest()}
        atomic_write_text(manifest_path, json.dumps(manifest, indent=2) + "\n")
        summary["dataset"] = manifest
    if cfg.exclude_hf_datasets:
        if not cfg.exclude_ids_path:
            raise SystemExit("exclude_hf_datasets is set but exclude_ids_path is not")
        ids: set[str] = set()
        sources = {}
        for ref in cfg.exclude_hf_datasets:
            repo, revision = _split_ref(ref)
            count = 0
            for name in _parquet_files(fs, repo, revision, None):
                table = pq.read_table(name, columns=["instance_id"], filesystem=fs)
                values = [v for v in table.column("instance_id").to_pylist() if v]
                ids.update(values)
                count += len(values)
            sources[ref] = count
        atomic_write_text(Path(cfg.exclude_ids_path), "\n".join(sorted(ids)) + "\n")
        summary["exclude_ids"] = {"path": cfg.exclude_ids_path, "unique": len(ids),
                                  "rows_per_source": sources}
    return summary
