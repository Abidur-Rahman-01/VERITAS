import os
import shutil
import stat
from pathlib import Path

def safe_rmtree(p):
    p = Path(p)
    if not p.exists():
        return
    def on_exc(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception as e:
            print(f"Error removing {path}: {e}")
    shutil.rmtree(p, onerror=on_exc)

# 1. Delete runs/
runs_dir = Path("runs")
if runs_dir.exists():
    for item in runs_dir.iterdir():
        print(f"Deleting {item}...")
        if item.is_dir():
            safe_rmtree(item)
        else:
            item.chmod(stat.S_IWRITE)
            item.unlink()
    print("runs/ directory cleared successfully.")

# 2. Delete results/ records if any
results_dir = Path("results")
if results_dir.exists():
    for item in results_dir.iterdir():
        print(f"Deleting {item}...")
        if item.is_dir():
            safe_rmtree(item)
        else:
            item.chmod(stat.S_IWRITE)
            item.unlink()
    print("results/ directory cleared successfully.")

print("All results and records deleted successfully.")
