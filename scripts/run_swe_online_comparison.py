import json
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

def main():
    policies = ["never", "always", "error_impact", "rcvov"]
    budget = 0.2
    task_id = "swe:astropy__astropy-13075"
    results = []

    print(f"=== Running Online Policy Comparison on SWE Task: {task_id} ===")

    for policy in policies:
        out_dir = Path(f"runs/swe-online-{policy}")
        need_run = not (out_dir / "summaries.jsonl").exists() or not (out_dir / "events.sqlite").exists()
        runtime = 0.0

        if need_run:
            if out_dir.exists():
                shutil.rmtree(out_dir, ignore_errors=True)

            cmd = [
                "uv", "run", "veritas", "collect",
                "--config", "configs/experiment.yaml",
                "--tasks", "data/prepared",
                "--source", "swe_test",
                "--split", "dev",
                "--limit", "1",
                "--images", "artifacts/swe-dev-map.json",
                "--policy", policy,
                "--budget", str(budget),
                "--artifact", "artifacts/calibration.json",
                "--tuning", "artifacts/tuning.json",
                "--output", str(out_dir)
            ]

            print(f"\n>>> Running SWE Online Policy: {policy} (budget={budget})")
            t0 = time.monotonic()
            res = subprocess.run(cmd, capture_output=True, text=True)
            runtime = time.monotonic() - t0

            if res.returncode != 0:
                print(f"Error running {policy}: {res.stderr}")
                continue
        else:
            print(f"\n>>> Reusing existing run data for {policy} from {out_dir}")

        summaries_file = out_dir / "summaries.jsonl"
        summaries = [json.loads(line) for line in summaries_file.read_text().splitlines() if line.strip()]

        # Read events from events.sqlite to count false rejections and caught errors
        db_path = out_dir / "events.sqlite"
        events = []
        if db_path.exists():
            con = sqlite3.connect(db_path)
            events = [json.loads(row[0]) for row in con.execute("SELECT payload FROM events").fetchall()]
            con.close()

        total_tokens = sum(s.get("total_online_tokens", 0) for s in summaries)
        
        # Check generated patch
        pred_file = out_dir / "predictions.jsonl"
        has_patch = False
        patch_len = 0
        if pred_file.exists():
            preds = [json.loads(l) for l in pred_file.read_text().splitlines() if l.strip()]
            if preds and preds[0].get("model_patch"):
                has_patch = True
                patch_len = len(preds[0]["model_patch"])

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

        verifications_performed = sum(1 for e in events if e.get("decision") == "verify")
        steps_count = len(events)

        row_res = {
            "policy": policy,
            "steps": steps_count,
            "has_patch": has_patch,
            "patch_chars": patch_len,
            "false_rejections": false_rejections,
            "errors_caught": errors_caught,
            "verifications": verifications_performed,
            "total_tokens": total_tokens,
            "runtime_s": round(runtime if runtime > 0 else (summaries[0].get("seconds", 0.0) if summaries else 0.0), 2)
        }
        results.append(row_res)
        print(f"[{policy}] Steps: {steps_count}, Patch: {has_patch} ({patch_len} chars), Verifications: {verifications_performed}, Tokens: {total_tokens}, Time: {runtime:.2f}s")

    print("\n" + "="*80)
    print("FINAL SWE ONLINE POLICY BENCHMARK RESULTS")
    print("="*80)
    print(f"{'Policy':<15} | {'Patch Generated':<16} | {'False Rej.':<10} | {'Errors Caught':<13} | {'Verifications':<14} | {'Total Tokens':<12} | {'Runtime (s)':<10}")
    print("-" * 105)
    for r in results:
        patch_str = f"Yes ({r['patch_chars']} chars)" if r['has_patch'] else "No"
        print(f"{r['policy']:<15} | {patch_str:<16} | {r['false_rejections']:<10} | {r['errors_caught']:<13} | {r['verifications']:<14} | {r['total_tokens']:<12} | {r['runtime_s']:<10}")
    print("-" * 105)

    with open("artifacts/swe_online_comparison.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Saved results to artifacts/swe_online_comparison.json")

if __name__ == "__main__":
    main()
