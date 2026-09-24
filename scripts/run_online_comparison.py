import subprocess
import json
import time
from pathlib import Path

policies = ["never", "always", "error_impact", "rcvov"]
tasks_limit = 5
budget = 0.2

results = []

for policy in policies:
    out_dir = Path(f"runs/online-{policy}")
    if out_dir.exists():
        import shutil
        shutil.rmtree(out_dir)
        
    cmd = [
        "uv", "run", "veritas", "collect",
        "--config", "configs/experiment.yaml",
        "--source", "gsm8k_test",
        "--split", "test",
        "--limit", str(tasks_limit),
        "--policy", policy,
        "--budget", str(budget),
        "--artifact", "artifacts/calibration.json",
        "--tuning", "artifacts/tuning.json",
        "--output", str(out_dir)
    ]
    print(f"\n>>> Running Online Policy: {policy} (limit={tasks_limit}, budget={budget})")
    t0 = time.monotonic()
    res = subprocess.run(cmd, capture_output=True, text=True)
    runtime = time.monotonic() - t0
    
    if res.returncode != 0:
        print(f"Error in {policy}: {res.stderr}")
        continue
        
    summaries_file = out_dir / "summaries.jsonl"
    summaries = [json.loads(line) for line in summaries_file.read_text().splitlines() if line.strip()]
    
    # Read events from events.sqlite to count false rejections and caught errors
    import sqlite3
    con = sqlite3.connect(out_dir / "events.sqlite")
    events = [json.loads(row[0]) for row in con.execute("SELECT payload FROM events").fetchall()]
    
    task_success_count = sum(1 for s in summaries if s.get("task_success"))
    total_tokens = sum(s.get("total_online_tokens", 0) for s in summaries)
    
    # False rejections: action was correct (error_label=0), but verifier returned FAIL and blocked it
    false_rejections = sum(
        1 for e in events 
        if e.get("decision") == "verify" 
        and e.get("verification", {}).get("verdict") == "FAIL"
        and e.get("error_label") == 0
    )
    
    # Errors caught: action was an error (error_label=1), verifier returned FAIL and caught it
    errors_caught = sum(
        1 for e in events 
        if e.get("decision") == "verify" 
        and e.get("verification", {}).get("verdict") == "FAIL"
        and e.get("error_label") == 1
    )
    
    results.append({
        "policy": policy,
        "task_success": f"{task_success_count}/{len(summaries)} ({task_success_count/len(summaries)*100:.1f}%)",
        "false_rejections": false_rejections,
        "errors_caught": errors_caught,
        "total_tokens": total_tokens,
        "runtime": f"{runtime:.2f}s"
    })

print("\n" + "="*85)
print("ONLINE POLICY COMPARISON RESULTS")
print("="*85)
print(f"| {'Policy':<14} | {'Task success':<14} | {'False rejections':<16} | {'Errors caught':<14} | {'Total tokens':<13} | {'Runtime':<10} |")
print("|" + "-"*16 + "|" + "-"*16 + "|" + "-"*18 + "|" + "-"*16 + "|" + "-"*15 + "|" + "-"*12 + "|")
for r in results:
    print(f"| {r['policy']:<14} | {r['task_success']:<14} | {r['false_rejections']:<16} | {r['errors_caught']:<14} | {r['total_tokens']:<13} | {r['runtime']:<10} |")
print("="*85)

write_json = Path("artifacts/online_policy_comparison.json")
write_json.write_text(json.dumps(results, indent=2))
