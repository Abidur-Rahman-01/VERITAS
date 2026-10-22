import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pyarrow.parquet as pq

from scripts.veritas_cloud_worker import evaluate_task_in_container

PARQUET = Path("data/swe_rebench_v2/data/train-00000-of-00001.parquet")
t = pq.read_table(str(PARQUET))
iid = "benchopt__benchopt-697"
idx = [i for i, id in enumerate(t["instance_id"].to_pylist()) if id == iid][0]

image_name = "swerebenchv2/benchopt-benchopt:697-ffd91c0"
test_patch = t["test_patch"][idx].as_py()
test_cmd = t["install_config"][idx].as_py()["test_cmd"]
ftp = t["FAIL_TO_PASS"][idx].as_py()
ptp = t["PASS_TO_PASS"][idx].as_py()

print(f"Evaluating {iid} in {image_name}...")
res = evaluate_task_in_container(
    image_name=image_name,
    patch="",
    test_patch=test_patch,
    test_cmd=test_cmd,
    fail_to_pass=ftp,
    pass_to_pass=ptp,
    timeout_seconds=60,
)

print("\n--- Evaluation Result ---")
for k, v in res.items():
    if k != "log":
        print(f"  {k}: {v}")
print(f"Log excerpt (tail 500 chars):\n{res.get('log', '')[-500:]}")
