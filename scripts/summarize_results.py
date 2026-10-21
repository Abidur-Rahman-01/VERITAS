import json
from collections import defaultdict
from pathlib import Path

results_file = Path("runs/feedback_study_pilot/results.jsonl")
results = [json.loads(line) for line in results_file.read_text(encoding="utf-8").splitlines() if line.strip()]

print(f"Total result rows: {len(results)}")

by_arm = defaultdict(list)
for r in results:
    by_arm[r["arm"]].append(r)

print("\n--- 5-ARM COMPARATIVE PERFORMANCE ---")
for arm in ["generic_retry", "raw_diagnostics", "fixed_actionable", "fixed_combined", "adaptive"]:
    rows = by_arm[arm]
    resolved_count = sum(r["resolved"] for r in rows)
    recovery_count = sum(r["resolved"] for r in rows if r["parent_resolved"] is False)
    total_incorrect = sum(1 for r in rows if r["parent_resolved"] is False)
    regression_count = sum(not r["resolved"] for r in rows if r["parent_resolved"] is True)
    total_correct = sum(1 for r in rows if r["parent_resolved"] is True)
    mean_credits = sum(r["total_credits"] for r in rows) / len(rows)
    mean_steps = sum(r["steps"] for r in rows) / len(rows)
    mean_time = sum(r["wall_seconds"] for r in rows) / len(rows)
    mean_cps = sum(r["checkpoints"] for r in rows) / len(rows)
    
    rec_pct = (recovery_count / total_incorrect * 100) if total_incorrect else 0
    reg_pct = (regression_count / total_correct * 100) if total_correct else 0
    all_pct = resolved_count / len(rows) * 100

    print(f"{arm:18s} | Overall: {resolved_count}/{len(rows)} ({all_pct:.1f}%) | Recovery: {recovery_count}/{total_incorrect} ({rec_pct:.1f}%) | Regression: {regression_count}/{total_correct} ({reg_pct:.1f}%) | Credits: {mean_credits:.3f} | Checkpoints: {mean_cps:.1f} | Time: {mean_time:.2f}s")

print("\n--- BY-BLOCK PAIRED BREAKDOWN ---")
blocks = defaultdict(dict)
for r in results:
    blocks[r["block_id"]][r["arm"]] = r

for b_id, b_arms in blocks.items():
    sample = next(iter(b_arms.values()))
    parent_res = sample["parent_resolved"]
    task = sample["task_id"]
    repo = sample["repository"]
    part = sample["partition"]
    p_status = "CORRECT (Parent Resolved)" if parent_res else "INCORRECT (Parent Failed)"
    print(f"\nBlock {b_id[:10]} | Task: {task:18s} | Repo: {repo:22s} | Partition: {part:12s} | Parent: {p_status}")
    for arm in ["generic_retry", "raw_diagnostics", "fixed_actionable", "fixed_combined", "adaptive"]:
        res = b_arms[arm]
        status = "RESOLVED (+)" if res["resolved"] else "UNRESOLVED (-)"
        print(f"   {arm:18s}: {status} (credits: {res['total_credits']:.3f}, checkpoints: {res['checkpoints']}, time: {res['wall_seconds']:.1f}s)")
