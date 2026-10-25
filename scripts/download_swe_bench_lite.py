import hashlib
import json
import os
import sys
import time
from pathlib import Path
from huggingface_hub import snapshot_download
import pandas as pd

DEST_DIR = Path("data/swe_bench_lite")
REPO_ID = "SWE-bench/SWE-bench_Lite"

print(f"Starting download of official dataset: {REPO_ID}")
start_time = time.time()

DEST_DIR.mkdir(parents=True, exist_ok=True)

local_path = snapshot_download(
    repo_id=REPO_ID,
    repo_type="dataset",
    local_dir=str(DEST_DIR),
)

elapsed = time.time() - start_time
print(f"Download completed in {elapsed:.2f} seconds to {DEST_DIR.resolve()}")

# Audit downloaded files
print("\n=== Dataset Audit ===")
manifest = {}
for path in sorted(DEST_DIR.rglob("*")):
    if path.is_file() and not path.name.startswith(".git"):
        rel = str(path.relative_to(DEST_DIR))
        size = path.stat().st_size
        h = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest[rel] = {"size_bytes": size, "sha256": h}
        print(f"  {rel:35s} | Size: {size:10,d} bytes | SHA256: {h[:16]}...")

# Inspect test and dev splits
for split_name in ["test", "dev"]:
    parquet_files = list(DEST_DIR.glob(f"**/{split_name}*.parquet"))
    if parquet_files:
        df = pd.read_parquet(parquet_files[0])
        print(f"\n--- Split: {split_name} ---")
        print(f"  Rows: {len(df)}")
        print(f"  Columns ({len(df.columns)}): {list(df.columns)}")
        if "repo" in df.columns:
            repos = df["repo"].value_counts().to_dict()
            print(f"  Distinct Repositories ({len(repos)}):")
            for repo, count in list(repos.items())[:10]:
                print(f"    - {repo:30s}: {count:3d} tasks")
            if len(repos) > 10:
                print(f"    ... and {len(repos) - 10} more repos")

manifest_file = DEST_DIR / "dataset_manifest.json"
manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"\nSaved manifest to {manifest_file}")
