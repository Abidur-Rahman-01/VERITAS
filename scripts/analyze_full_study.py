import json
from collections import defaultdict
from pathlib import Path

results_file = Path("runs/feedback_study_full/results.jsonl")
results = [json.loads(line) for line in results_file.read_text(encoding="utf-8").splitlines() if line.strip()]

print(f"Total result rows: {len(results)}")

by_arm = defaultdict(list)
for r in results:
    by_arm[r["arm"]].append(r)

print("\n--- FULL 60-TASK (300-BRANCH) 5-ARM COMPARATIVE PERFORMANCE ---")
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

by_partition = defaultdict(lambda: defaultdict(list))
for r in results:
    by_partition[r["partition"]][r["arm"]].append(r)

print("\n--- BREAKDOWN BY PARTITION (DEVELOPMENT vs CONFIRMATION) ---")
for part in ["development", "confirmation"]:
    n_blocks = len(by_partition[part]["generic_retry"])
    print(f"\nPartition: {part.upper()} ({n_blocks} blocks)")
    for arm in ["generic_retry", "raw_diagnostics", "fixed_actionable", "fixed_combined", "adaptive"]:
        rows = by_partition[part][arm]
        res = sum(r["resolved"] for r in rows)
        rec = sum(r["resolved"] for r in rows if r["parent_resolved"] is False)
        tot_inc = sum(1 for r in rows if r["parent_resolved"] is False)
        reg = sum(not r["resolved"] for r in rows if r["parent_resolved"] is True)
        tot_cor = sum(1 for r in rows if r["parent_resolved"] is True)
        mean_c = sum(r["total_credits"] for r in rows) / len(rows)
        print(f"   {arm:18s}: {res}/{len(rows)} resolved ({res/len(rows)*100:.1f}%) | Recovery: {rec}/{tot_inc} | Regression: {reg}/{tot_cor} | Credits: {mean_c:.3f}")
