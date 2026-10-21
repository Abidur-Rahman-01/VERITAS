"""
Download and verify nebius/SWE-rebench-V2 from Hugging Face.
Saves to data/swe_rebench_v2/
"""
import os
import sys
from pathlib import Path
from huggingface_hub import snapshot_download, hf_hub_download
import pyarrow.parquet as pq

TARGET_DIR = Path("data/swe_rebench_v2")
REPO_ID = "nebius/SWE-rebench-V2"

def main():
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {REPO_ID} to {TARGET_DIR}...")
    
    # Download the entire repo or parquet directly
    local_dir = snapshot_download(
        repo_id=REPO_ID,
        repo_type="dataset",
        local_dir=str(TARGET_DIR),
        local_dir_use_symlinks=False
    )
    print(f"Successfully downloaded to {local_dir}")
    
    # Verify the parquet file
    parquet_files = list(TARGET_DIR.glob("**/*.parquet"))
    print(f"Found {len(parquet_files)} parquet file(s):")
    total_rows = 0
    for p in parquet_files:
        table = pq.read_table(p)
        print(f"  - {p.name}: {table.num_rows:,} rows, {table.num_columns} columns, {p.stat().st_size / (1024*1024):.2f} MB")
        total_rows += table.num_rows
        print(f"    Columns: {table.column_names[:10]} ...")
        
    print(f"\nTotal dataset rows across splits: {total_rows:,}")

if __name__ == "__main__":
    main()
