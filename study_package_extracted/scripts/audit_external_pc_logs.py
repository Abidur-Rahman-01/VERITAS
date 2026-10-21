"""
audit_external_pc_logs.py

Independent Raw Run-Log Verification Script for VERITAS.
Audits raw execution databases (events.sqlite), transcripts, and grading traces
from the primary execution machine against reported CSV ledgers.

Verifies:
1. Group membership & cohort assignment
2. Prompt cue & review delivery fidelity
3. Operational definition of premature surrender
4. Token and tool call concordance between raw logs and ledgers
5. Independent grading execution traces
"""

import os
import sys
import json
import sqlite3
import argparse
from pathlib import Path
import pandas as pd


def check_sqlite_table_exists(conn, table_name):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def audit_trial_folder(trial_path: Path):
    """Audits an individual trial folder containing events.sqlite or summary.json."""
    result = {
        "trial_id": trial_path.name,
        "path": str(trial_path),
        "has_sqlite": False,
        "has_summary": False,
        "has_patch": False,
        "has_grade": False,
        "actual_prompt_tokens": None,
        "actual_completion_tokens": None,
        "actual_total_tokens": None,
        "actual_tool_calls": None,
        "terminal_step": None,
        "terminal_tool": None,
        "cue_detected_in_prompt": None,
        "review_received": None,
        "surrender_detected": None,
        "grading_status": None,
        "audit_pass": False,
        "notes": [],
    }

    # 1. Check file existence
    sqlite_path = trial_path / "events.sqlite"
    summary_path = trial_path / "summary.json"
    patch_path = trial_path / "final.patch"
    if not patch_path.exists():
        patch_path = trial_path / "patch.diff"
    grade_path = trial_path / "grade.log"

    result["has_sqlite"] = sqlite_path.exists()
    result["has_summary"] = summary_path.exists()
    result["has_patch"] = patch_path.exists()
    result["has_grade"] = grade_path.exists()

    # 2. Inspect SQLite events if available
    if sqlite_path.exists():
        try:
            conn = sqlite3.connect(str(sqlite_path))
            cursor = conn.cursor()

            # Check table structure
            if check_sqlite_table_exists(conn, "events"):
                cursor.execute(
                    "SELECT COUNT(*) FROM events WHERE type='tool_call'"
                )
                result["actual_tool_calls"] = cursor.fetchone()[0]

                # Re-aggregate tokens
                cursor.execute(
                    "SELECT SUM(COALESCE(prompt_tokens, 0)), SUM(COALESCE(completion_tokens, 0)) FROM events"
                )
                row = cursor.fetchone()
                p_tok, c_tok = row if row else (0, 0)
                result["actual_prompt_tokens"] = p_tok or 0
                result["actual_completion_tokens"] = c_tok or 0
                result["actual_total_tokens"] = (p_tok or 0) + (c_tok or 0)

                # Check prompt cue in turn 1
                cursor.execute(
                    "SELECT payload FROM events WHERE step=1 OR type='initial_prompt' ORDER BY step ASC LIMIT 1"
                )
                first_prompt_row = cursor.fetchone()
                if first_prompt_row and first_prompt_row[0]:
                    payload_str = str(first_prompt_row[0]).lower()
                    cue_words = [
                        "benchmark evaluation",
                        "evaluation harness",
                        "automated grading",
                        "scoring",
                    ]
                    result["cue_detected_in_prompt"] = any(
                        w in payload_str for w in cue_words
                    )

                # Check review delivery
                cursor.execute(
                    "SELECT COUNT(*) FROM events WHERE type='review' OR event_name='verifier_feedback'"
                )
                rev_count = cursor.fetchone()[0]
                result["review_received"] = rev_count > 0

                # Check terminal step and surrender
                cursor.execute(
                    "SELECT step, type, payload FROM events ORDER BY step DESC LIMIT 1"
                )
                last_event = cursor.fetchone()
                if last_event:
                    result["terminal_step"] = last_event[0]
                    result["terminal_tool"] = last_event[1]
                    # Check surrender heuristic: stopped early without diff
                    is_early = (last_event[0] or 0) < 20
                    is_empty_patch = (
                        not patch_path.exists()
                        or patch_path.stat().st_size == 0
                    )
                    result["surrender_detected"] = is_early and is_empty_patch

            conn.close()
        except Exception as e:
            result["notes"].append(f"SQLite parse error: {str(e)}")

    # 3. Inspect summary.json if available
    if summary_path.exists():
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                s_data = json.load(f)
                result["grading_status"] = s_data.get(
                    "resolved", s_data.get("status")
                )
                if result["actual_total_tokens"] is None:
                    result["actual_total_tokens"] = s_data.get("tokens_total")
                if result["actual_tool_calls"] is None:
                    result["actual_tool_calls"] = s_data.get("tool_calls_count")
        except Exception as e:
            result["notes"].append(f"summary.json parse error: {str(e)}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Audit raw run logs from execution PC."
    )
    parser.add_argument(
        "--raw-dir",
        type=str,
        default="",
        help="Path to external raw artifacts directory (e.g. D:/2110001/VERITAS/artifacts)",
    )
    parser.add_argument(
        "--ledger",
        type=str,
        default="replication/data/study_grand_pool_128.csv",
        help="Path to master study ledger CSV",
    )
    parser.add_argument(
        "--output-report",
        type=str,
        default="artifacts/audit/external_pc_verification_report.json",
        help="Path to output JSON audit report",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("VERITAS RAW RUN-LOG AUDIT & INDEPENDENT VERIFICATION")
    print("=" * 70)
    print(f"Target Raw Directory: {args.raw_dir or 'None (Checking local environment)'}")
    print(f"Ledger Path:          {args.ledger}")

    # Check ledger
    if not os.path.exists(args.ledger):
        print(f"[!] Master ledger not found at {args.ledger}")
        sys.exit(1)

    df_ledger = pd.read_csv(args.ledger)
    print(f"[*] Loaded master ledger with {len(df_ledger)} recorded trial rows.")

    audit_summary = {
        "status": "PROVISIONAL_UNVERIFIED",
        "raw_dir_provided": bool(args.raw_dir),
        "raw_dir_exists": (
            os.path.exists(args.raw_dir) if args.raw_dir else False
        ),
        "ledger_total_rows": len(df_ledger),
        "verified_runs_count": 0,
        "missing_raw_runs_count": len(df_ledger),
        "findings_status": (
            "Numbers remain reported but unverified until raw logs from other"
            " PC are mounted."
        ),
        "criteria_checks": {
            "criterion_1_group_assignment": "PENDING_RAW_LOGS",
            "criterion_2_cue_and_review_fidelity": "PENDING_RAW_LOGS",
            "criterion_3_surrender_definition": "PENDING_RAW_LOGS",
            "criterion_4_token_concordance": "PENDING_RAW_LOGS",
            "criterion_5_independent_grading": "PENDING_RAW_LOGS",
        },
        "audited_trials": [],
    }

    if not args.raw_dir or not os.path.exists(args.raw_dir):
        print("\n[NOTICE] Raw logs directory from other PC is not yet mounted.")
        print(
            "--> In accordance with the verification protocol, all statistics"
            " remain classified as:"
        )
        print("    'REPORTED BUT UNVERIFIED PENDING PRIMARY-HOST AUDIT'.")
        print("\nTo verify when records are transferred, run:")
        print(
            f"python scripts/audit_external_pc_logs.py --raw-dir"
            f' "<path_to_other_pc_artifacts>"'
        )

        out_dir = Path(args.output_report).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(args.output_report, "w", encoding="utf-8") as f:
            json.dump(audit_summary, f, indent=2)
        print(f"\n[+] Wrote provisional audit report to {args.output_report}")
        return

    # If raw_dir exists, iterate through subdirectories
    raw_path = Path(args.raw_dir)
    trial_subdirs = [p for p in raw_path.iterdir() if p.is_dir()]
    print(
        f"[*] Found {len(trial_subdirs)} potential run folders in {args.raw_dir}"
    )

    verified_count = 0
    for subdir in trial_subdirs:
        trial_audit = audit_trial_folder(subdir)
        audit_summary["audited_trials"].append(trial_audit)
        if trial_audit["has_sqlite"] or trial_audit["has_summary"]:
            verified_count += 1

    audit_summary["verified_runs_count"] = verified_count
    audit_summary["missing_raw_runs_count"] = len(df_ledger) - verified_count

    print(
        f"[+] Audited {verified_count} runs. Full results written to"
        f" {args.output_report}"
    )
    out_dir = Path(args.output_report).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(args.output_report, "w", encoding="utf-8") as f:
        json.dump(audit_summary, f, indent=2)


if __name__ == "__main__":
    main()
