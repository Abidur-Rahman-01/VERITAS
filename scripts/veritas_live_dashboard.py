#!/usr/bin/env python3
"""
VERITAS Live Experiment Monitor & Web Dashboard
Serves an auto-refreshing real-time UI on http://localhost:8765
Supports OpenHands SWE-bench Lite runs and the paired feedback study.
"""

import http.server
import json
import os
import re
import sqlite3
import socketserver
import sys
from collections import defaultdict
from pathlib import Path

PORT = int(os.environ.get("VERITAS_DASHBOARD_PORT", "8765"))

SWE_LITE_DIR = Path(os.environ.get("SWE_LITE_DIR", "runs/openhands-swe-lite"))
FEEDBACK_DIR = Path(os.environ.get("FEEDBACK_STUDY_DIR", "runs/feedback_study_v2_500"))
FEEDBACK_LOG = Path(os.environ.get("FEEDBACK_LOG", FEEDBACK_DIR / "run.log"))


def get_swe_lite_stats():
    total_tasks = 300
    tasks_file = Path("data/swebench_lite.jsonl")
    if tasks_file.exists():
        try:
            total_tasks = len([l for l in tasks_file.read_text(encoding="utf-8").splitlines() if l.strip()])
        except Exception:
            pass

    agent_results_file = SWE_LITE_DIR / "agent_results.jsonl"
    records = []
    if agent_results_file.exists():
        try:
            for l in agent_results_file.read_text(encoding="utf-8").splitlines():
                if l.strip():
                    records.append(json.loads(l))
        except Exception:
            pass

    completed_count = sum(1 for r in records if r.get("openhands_exit_code") == 0)
    patch_count = sum(1 for r in records if r.get("model_patch"))

    logs_dir = SWE_LITE_DIR / "openhands-logs"
    latest_log = None
    live_log_tail = ""
    if logs_dir.is_dir():
        log_files = list(logs_dir.glob("*.jsonl"))
        if log_files:
            latest_log = max(log_files, key=lambda p: p.stat().st_mtime)
            try:
                live_log_tail = "\n".join(
                    latest_log.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
                )
            except OSError:
                live_log_tail = ""

    repos_dir = SWE_LITE_DIR / "repos"
    active_repo = "Initializing..."
    active_task = "-"
    if repos_dir.is_dir():
        subdirs = sorted(repos_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if subdirs:
            active_task = subdirs[0].name
            active_repo = active_task.split("__")[0] if "__" in active_task else active_task

    recorded_ids = {r.get("instance_id") for r in records}
    if latest_log:
        if latest_log.stem not in recorded_ids:
            active_task = latest_log.stem
            active_repo = active_task.split("__")[0] if "__" in active_task else active_task
        else:
            active_task = "-"
            active_repo = "No active task"

    last_record = records[-1] if records else {}
    if not records and active_task != "-":
        last_task = active_task
    else:
        last_task = last_record.get("instance_id", active_task)

    recent_feed = []
    for r in records[-15:]:
        inst = r.get("instance_id", "unknown")
        model = r.get("model_name_or_path", "codestral:22b")
        exit_code = r.get("openhands_exit_code")
        completed = exit_code == 0
        reason = r.get("error") or ("Agent exited successfully" if completed else "Agent did not complete")
        recent_feed.append({
            "task_id": inst,
            "model": model,
            "agent": "OpenHands CLI",
            "completed": completed,
            "patch_present": bool(r.get("model_patch")),
            "exit_code": exit_code,
            "reason": reason[:160],
        })

    return {
        "mode": "swe_lite",
        "benchmark_title": "SWE-bench Lite OpenHands Benchmark",
        "benchmark_subtitle": "Agent: OpenHands CLI | Grader: official SWE-bench harness on Modal",
        "total_tasks": total_tasks,
        "completed_tasks": len(records),
        "agent_finished": completed_count,
        "patches_present": patch_count,
        "active_repo": active_repo,
        "active_task": active_task,
        "last_task": last_task,
        "live_log_tail": live_log_tail,
        "recent_feed": recent_feed,
    }


def get_feedback_stats():
    total_blocks = 500
    blocks_file = FEEDBACK_DIR / "blocks.jsonl"
    if blocks_file.exists():
        try:
            total_blocks = len([l for l in blocks_file.read_text(encoding="utf-8").splitlines() if l.strip()])
        except Exception:
            pass

    results_file = FEEDBACK_DIR / "results.jsonl"
    records = []
    if results_file.exists():
        try:
            for l in results_file.read_text(encoding="utf-8").splitlines():
                if l.strip():
                    records.append(json.loads(l))
        except Exception:
            pass

    by_arm = defaultdict(lambda: {"count": 0, "resolved": 0, "credits": 0.0, "time": 0.0})
    completed_blocks = set()

    for r in records:
        arm = r.get("arm", "unknown")
        by_arm[arm]["count"] += 1
        if r.get("resolved"):
            by_arm[arm]["resolved"] += 1
        by_arm[arm]["credits"] += r.get("total_credits", 0.0)
        by_arm[arm]["time"] += r.get("wall_seconds", 0.0)
        completed_blocks.add(r.get("block_id"))

    arm_table = []
    for arm in ["generic_retry", "raw_diagnostics", "fixed_actionable", "fixed_combined", "adaptive"]:
        st = by_arm[arm]
        cnt = st["count"]
        res = st["resolved"]
        rate = (res / cnt * 100) if cnt > 0 else 0.0
        m_cred = (st["credits"] / cnt) if cnt > 0 else 0.0
        m_time = (st["time"] / cnt) if cnt > 0 else 0.0
        arm_table.append({
            "arm": arm,
            "count": cnt,
            "resolved": res,
            "rate": round(rate, 1),
            "mean_credits": round(m_cred, 3),
            "mean_time": round(m_time, 1),
        })

    last_record = records[-1] if records else {}

    return {
        "mode": "feedback_study",
        "benchmark_title": "VERITAS Paired Feedback-Selection Benchmark",
        "benchmark_subtitle": "500-Task SWE-rebench-V2 Runtime Evaluation",
        "total_blocks": total_blocks,
        "completed_blocks": len(completed_blocks),
        "total_branches_completed": len(records),
        "total_planned_branches": total_blocks * 5,
        "last_task": last_record.get("task_id", "Initializing..."),
        "last_repo": last_record.get("repository", "Altair / SWE-rebench"),
        "arm_stats": arm_table,
        "recent_records": records[-10:] if records else [],
    }


def get_feedback_paper_stats():
    """Live descriptive metrics for one frozen paired feedback study."""
    def read_jsonl(path):
        rows = []
        if not path.is_file():
            return rows
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                if line.strip():
                    rows.append(json.loads(line))
            except ValueError:
                continue  # Ignore a partially written final record while the run is active.
        return rows

    blocks = read_jsonl(FEEDBACK_DIR / "blocks.jsonl")
    branches = read_jsonl(FEEDBACK_DIR / "branches.jsonl")
    records = read_jsonl(FEEDBACK_DIR / "results.jsonl")
    total_blocks = len(blocks)
    total_branches = len(branches)
    by_arm = defaultdict(lambda: {
        "count": 0, "graded": 0, "resolved": 0, "infra": 0,
        "credits": 0.0, "seconds": 0.0, "prompt_tokens": 0,
        "completion_tokens": 0, "usage_complete": 0,
        "recovery_n": 0, "recovered": 0, "regression_n": 0,
        "regressions": 0, "recovery_tokens": 0, "recovery_credits": 0.0,
        "mean_checkpoints": 0,
    })
    block_arms = defaultdict(dict)
    for row in records:
        arm = row.get("arm", "unknown")
        stat = by_arm[arm]
        stat["count"] += 1
        if isinstance(row.get("resolved"), bool):
            stat["graded"] += 1
            stat["resolved"] += int(row["resolved"])
        if row.get("resolved") is None or row.get("grader_status") == "infrastructure_error":
            stat["infra"] += 1
        stat["credits"] += float(row.get("total_credits") or 0.0)
        stat["seconds"] += float(row.get("wall_seconds") or 0.0)
        stat["prompt_tokens"] += int(row.get("actor_prompt_tokens") or 0)
        stat["completion_tokens"] += int(row.get("actor_completion_tokens") or 0)
        stat["usage_complete"] += int(bool(row.get("actor_usage_complete")))
        if row.get("parent_resolved") is False and isinstance(row.get("resolved"), bool):
            stat["recovery_n"] += 1
            stat["recovered"] += int(row["resolved"])
            stat["recovery_tokens"] += int(row.get("actor_prompt_tokens") or 0) + int(row.get("actor_completion_tokens") or 0)
            stat["recovery_credits"] += float(row.get("total_credits") or 0.0)
        if row.get("parent_resolved") is True and isinstance(row.get("resolved"), bool):
            stat["regression_n"] += 1
            stat["regressions"] += int(not row["resolved"])
        stat["mean_checkpoints"] += int(row.get("checkpoints") or 0)
        block_arms[row.get("block_id")][arm] = row

    arm_order = ["generic_retry", "raw_diagnostics", "fixed_actionable", "fixed_combined", "adaptive"]
    arm_stats = []
    for arm in arm_order:
        stat = by_arm[arm]
        tokens = stat["prompt_tokens"] + stat["completion_tokens"]
        arm_stats.append({
            "arm": arm,
            "count": stat["count"],
            "graded": stat["graded"],
            "resolved": stat["resolved"],
            "unresolved": stat["graded"] - stat["resolved"],
            "infrastructure_errors": stat["infra"],
            "resolution_rate": round(stat["resolved"] / stat["graded"] * 100, 1) if stat["graded"] else None,
            "mean_credits": round(stat["credits"] / stat["count"], 3) if stat["count"] else None,
            "credits_per_resolution": round(stat["credits"] / stat["resolved"], 3) if stat["resolved"] else None,
            "mean_seconds": round(stat["seconds"] / stat["count"], 1) if stat["count"] else None,
            "prompt_tokens": stat["prompt_tokens"],
            "completion_tokens": stat["completion_tokens"],
            "tokens": tokens,
            "mean_tokens": round(tokens / stat["count"]) if stat["count"] else None,
            "mean_checkpoints": round(stat["mean_checkpoints"] / stat["count"], 2) if stat["count"] else None,
            "usage_complete": stat["usage_complete"],
            "recovery_resolved": stat["recovered"],
            "recovery_total": stat["recovery_n"],
            "recovery_tokens": stat["recovery_tokens"],
            "recoveries_per_1k_tokens": round(stat["recovered"] * 1000 / stat["recovery_tokens"], 3) if stat["recovery_tokens"] else None,
            "credits_per_recovery": round(stat["recovery_credits"] / stat["recovered"], 3) if stat["recovered"] else None,
            "regressions": stat["regressions"],
            "regression_total": stat["regression_n"],
            "resolved_per_1k_tokens": round(stat["resolved"] * 1000 / tokens, 3) if tokens else None,
        })

    draft_prompt = draft_completion = draft_measured = draft_steps = 0
    blocks_dir = FEEDBACK_DIR / "blocks"
    parent_grades = []
    if blocks_dir.is_dir():
        for grade_path in blocks_dir.glob("*/parent_grade.json"):
            try:
                parent_grades.append(json.loads(grade_path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        for db_path in blocks_dir.glob("*/draft_events.sqlite"):
            try:
                db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=0.25)
                try:
                    payloads = db.execute("SELECT payload FROM events").fetchall()
                finally:
                    db.close()
                for (payload,) in payloads:
                    usage = (json.loads(payload).get("policy_usage") or {})
                    draft_prompt += int(usage.get("prompt_tokens") or 0)
                    draft_completion += int(usage.get("completion_tokens") or 0)
                    draft_measured += int(bool(usage.get("measured")))
                    draft_steps += 1
            except (sqlite3.Error, OSError, ValueError, TypeError):
                continue

    graded_parents = [p for p in parent_grades if isinstance(p.get("parent_resolved"), bool)]
    parent_resolved = sum(bool(p["parent_resolved"]) for p in graded_parents)
    paired = {"n": 0, "adaptive_only": 0, "fixed_only": 0, "both_or_neither": 0,
              "adaptive_recovered": 0, "fixed_recovered": 0}
    for arm_rows in block_arms.values():
        adaptive = arm_rows.get("adaptive")
        fixed = arm_rows.get("fixed_actionable")
        if not adaptive or not fixed or adaptive.get("parent_resolved") is not False or fixed.get("parent_resolved") is not False:
            continue
        if not isinstance(adaptive.get("resolved"), bool) or not isinstance(fixed.get("resolved"), bool):
            continue
        paired["n"] += 1
        paired["adaptive_recovered"] += int(adaptive["resolved"])
        paired["fixed_recovered"] += int(fixed["resolved"])
        if adaptive["resolved"] and not fixed["resolved"]:
            paired["adaptive_only"] += 1
        elif fixed["resolved"] and not adaptive["resolved"]:
            paired["fixed_only"] += 1
        else:
            paired["both_or_neither"] += 1

    active = {"index": None, "total": total_blocks, "block": None, "task": None,
              "repository": None, "partition": None, "arm": None}
    log_tail = ""
    if FEEDBACK_LOG.is_file():
        try:
            with FEEDBACK_LOG.open("rb") as log_file:
                log_file.seek(0, os.SEEK_END)
                size = log_file.tell()
                log_file.seek(max(0, size - 160_000))
                tail_bytes = log_file.read()
            log_lines = tail_bytes.decode("utf-8", errors="replace").splitlines()
            log_tail = "\n".join(log_lines[-80:])
            block_pattern = re.compile(r"\[(\d+)/(\d+)\] Block (\S+) \(Task: ([^,]+), Repo: ([^,]+), Partition: ([^)]+)\)")
            arm_pattern = re.compile(r"Arm\s+(\w+)\s*:\s*starting paired continuation")
            last_arm_start = -1
            last_arm_finish = -1
            for index, line in enumerate(log_lines):
                if arm_pattern.search(line):
                    last_arm_start = index
                if "-> Final grade:" in line:
                    last_arm_finish = index
            for line in reversed(log_lines):
                match = block_pattern.search(line)
                if match:
                    active.update({"index": int(match.group(1)), "total": int(match.group(2)),
                                   "block": match.group(3), "task": match.group(4),
                                   "repository": match.group(5), "partition": match.group(6)})
                    break
            for line in reversed(log_lines):
                match = arm_pattern.search(line)
                if match:
                    if last_arm_start > last_arm_finish:
                        active["arm"] = match.group(1)
                    break
        except OSError:
            pass

    branch_tokens = sum(a["tokens"] for a in arm_stats)
    complete_blocks = sum(1 for arms in block_arms.values() if len(arms) >= 5)
    return {
        "mode": "feedback_paper",
        "benchmark_title": "VERITAS Feedback Study · Live Monitor",
        "benchmark_subtitle": f"{FEEDBACK_DIR.name} · descriptive pilot · results refresh every 2 seconds",
        "total_blocks": total_blocks,
        "total_branches": total_branches,
        "completed_blocks": complete_blocks,
        "completed_branches": len(records),
        "graded_parents": len(graded_parents),
        "parent_resolved": parent_resolved,
        "parent_incorrect": len(graded_parents) - parent_resolved,
        "parent_resolution_rate": round(parent_resolved * 100 / len(graded_parents), 1) if graded_parents else None,
        "draft": {"prompt_tokens": draft_prompt, "completion_tokens": draft_completion,
                  "tokens": draft_prompt + draft_completion, "steps": draft_steps,
                  "measured_steps": draft_measured,
                  "token_credit_estimate": round((draft_prompt + draft_completion) * 0.002, 3)},
        "revision": {"prompt_tokens": sum(a["prompt_tokens"] for a in arm_stats),
                     "completion_tokens": sum(a["completion_tokens"] for a in arm_stats),
                     "tokens": branch_tokens,
                     "reported_estimated_credits": round(sum(float(r.get("total_credits") or 0.0) for r in records), 3)},
        "all_actor_tokens": draft_prompt + draft_completion + branch_tokens,
        "paired": paired,
        "active": active,
        "live_log_tail": log_tail,
        "last_task": active.get("task") or (records[-1].get("task_id") if records else "Waiting for run log"),
        "last_repo": active.get("repository") or (records[-1].get("repository") if records else "-"),
        "arm_stats": arm_stats,
        "recent_records": records[-20:],
        "notes": [
            "Before feedback = shared parent draft token usage from draft_events.sqlite.",
            "After feedback = per-arm continuation usage recorded in results.jsonl.",
            "Credits are estimates and the reference cap is not enforced; usage completeness is reported per arm.",
            "All summaries are live descriptive counts; clustered confirmatory analysis is not performed here.",
        ],
    }


def get_stats():
    if os.environ.get("FEEDBACK_STUDY_DIR"):
        return get_feedback_paper_stats()
    if SWE_LITE_DIR.exists():
        return get_swe_lite_stats()
    return get_feedback_stats()


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VERITAS Live Benchmark Dashboard</title>
    <style>
        :root {
            --bg: #0d1117;
            --card-bg: #161b22;
            --border: #30363d;
            --text: #c9d1d9;
            --accent: #58a6ff;
            --green: #3fb950;
            --purple: #bc8cff;
            --orange: #f0883e;
            --red: #f85149;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 24px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 16px;
            margin-bottom: 24px;
        }
        .title {
            font-size: 24px;
            font-weight: 700;
            color: #f0f6fc;
        }
        .subtitle {
            color: #8b949e;
            font-size: 14px;
            margin-top: 4px;
        }
        .live-badge {
            background-color: rgba(63, 185, 80, 0.15);
            color: var(--green);
            border: 1px solid var(--green);
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 13px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .pulse {
            width: 8px;
            height: 8px;
            background: var(--green);
            border-radius: 50%;
            animation: blink 1.5s infinite;
        }
        @keyframes blink {
            0% { opacity: 0.2; }
            50% { opacity: 1; }
            100% { opacity: 0.2; }
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
        }
        .card-label {
            color: #8b949e;
            font-size: 13px;
            text-transform: uppercase;
            font-weight: 600;
            margin-bottom: 8px;
        }
        .card-val {
            font-size: 24px;
            font-weight: 700;
            color: #f0f6fc;
        }
        .progress-bar-container {
            width: 100%;
            height: 6px;
            background-color: var(--border);
            border-radius: 3px;
            margin-top: 10px;
            overflow: hidden;
        }
        .progress-bar {
            height: 100%;
            background-color: var(--accent);
            width: 0%;
            transition: width 0.4s ease;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            background-color: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 24px;
        }
        th, td {
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid var(--border);
            font-size: 13px;
        }
        th {
            background-color: #1c2128;
            color: #8b949e;
            font-weight: 600;
        }
        .terminal {
            background: #000;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            font-family: "Cascadia Code", Consolas, monospace;
            font-size: 13px;
            color: #7ee787;
            max-height: 280px;
            overflow-y: auto;
        }
        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        .badge-pass {
            background-color: rgba(63, 185, 80, 0.2);
            color: var(--green);
            border: 1px solid var(--green);
        }
        .badge-fail {
            background-color: rgba(248, 81, 73, 0.2);
            color: var(--red);
            border: 1px solid var(--red);
        }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="title" id="page-title">VERITAS Live Monitor</div>
            <div class="subtitle" id="page-subtitle">Actor: Codestral 22B | Verifier: Llama 3.1 8B</div>
        </div>
        <div class="live-badge">
            <div class="pulse"></div> LIVE ACTIVE
        </div>
    </div>

    <div class="grid">
        <div class="card">
            <div class="card-label">Task Progress</div>
            <div class="card-val" id="stat-progress">- / -</div>
            <div class="progress-bar-container">
                <div class="progress-bar" id="progress-bar"></div>
            </div>
        </div>
        <div class="card">
            <div class="card-label">OpenHands finished</div>
            <div class="card-val" id="stat-verified">-</div>
            <div style="font-size: 12px; color: #8b949e; margin-top: 6px;" id="stat-verified-sub">Patches produced: -</div>
        </div>
        <div class="card">
            <div class="card-label">Current Task</div>
            <div class="card-val" style="font-size: 16px; word-break: break-all;" id="stat-task">Initializing...</div>
            <div style="font-size: 12px; color: var(--accent); margin-top: 4px;" id="stat-repo">-</div>
        </div>
        <div class="card">
            <div class="card-label">Coding agent</div>
            <div class="card-val" style="font-size: 18px; color: var(--purple);">OpenHands</div>
            <div style="font-size: 12px; color: #8b949e; margin-top: 4px;">Repository navigation and repair</div>
        </div>
        <div class="card">
            <div class="card-label">Benchmark verifier</div>
            <div class="card-val" style="font-size: 18px; color: var(--orange);">Modal grader</div>
            <div style="font-size: 12px; color: #8b949e; margin-top: 4px;">Official SWE-bench tests</div>
        </div>
    </div>

    <h3 style="color: #f0f6fc; margin-bottom: 12px;">OpenHands Task Runs</h3>
    <table>
        <thead>
            <tr>
                <th>Instance ID</th>
                <th>Actor</th>
                <th>Agent</th>
                <th>Patch</th>
                <th>Process status</th>
                <th>Details</th>
            </tr>
        </thead>
        <tbody id="task-tbody">
            <tr><td colspan="6" style="text-align: center; color: #8b949e;">Waiting for completed tasks...</td></tr>
        </tbody>
    </table>

    <h3 style="color: #f0f6fc; margin-bottom: 12px;">Live Event Log</h3>
    <div class="terminal" id="terminal-feed">
        Waiting for stream records...
    </div>

    <script>
        async function updateDashboard() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();

                if (data.mode === 'swe_lite') {
                    document.getElementById('page-title').innerText = data.benchmark_title;
                    document.getElementById('page-subtitle').innerText = data.benchmark_subtitle;
                    document.getElementById('stat-progress').innerText = `${data.completed_tasks} / ${data.total_tasks}`;
                    
                    const pct = data.total_tasks > 0 ? (data.completed_tasks / data.total_tasks * 100).toFixed(1) : 0;
                    document.getElementById('progress-bar').style.width = `${pct}%`;
                    
                    document.getElementById('stat-verified').innerText = `${data.agent_finished} exited successfully`;
                    document.getElementById('stat-verified-sub').innerText = `Patches present: ${data.patches_present}`;
                    document.getElementById('stat-task').innerText = data.active_task || data.last_task;
                    document.getElementById('stat-repo').innerText = data.active_repo;

                    const tbody = document.getElementById('task-tbody');
                    if (data.recent_feed && data.recent_feed.length > 0) {
                        tbody.innerHTML = '';
                        data.recent_feed.slice().reverse().forEach(t => {
                            const row = document.createElement('tr');
                            const statusBadge = t.completed ? '<span class="badge badge-pass">EXIT 0</span>' : '<span class="badge badge-fail">INCOMPLETE</span>';
                            const patchBadge = t.patch_present ? '<span style="color: #3fb950;">YES</span>' : '<span style="color: #f85149;">NO</span>';
                            row.innerHTML = `
                                <td style="font-family: monospace; font-weight: bold; color: #58a6ff;">${t.task_id}</td>
                                <td>${t.model}</td>
                                <td><span style="color: #f0883e; font-weight: bold;">${t.agent}</span></td>
                                <td>${patchBadge}</td>
                                <td>${statusBadge} (${t.exit_code ?? 'running'})</td>
                                <td style="color: #c9d1d9; font-size: 12px;">${t.reason}</td>
                            `;
                            tbody.appendChild(row);
                        });

                        const term = document.getElementById('terminal-feed');
                        if (data.live_log_tail) {
                            term.textContent = data.live_log_tail;
                        } else {
                            term.innerHTML = data.recent_feed.map(t => {
                            const status = t.completed ? '[AGENT EXIT 0]' : '[AGENT INCOMPLETE]';
                            const color = t.completed ? '#3fb950' : '#f85149';
                            return `<div style="margin-bottom: 4px;"><span style="color: ${color}; font-weight: bold;">${status}</span> <span style="color: #58a6ff;">${t.task_id}</span> | Agent: <b>${t.agent}</b> | ${t.reason}</div>`;
                            }).join('');
                        }
                    }
                }
            } catch (err) {
                console.error(err);
            }
        }

        setInterval(updateDashboard, 2000);
        updateDashboard();
    </script>
</body>
</html>
"""


FEEDBACK_HTML_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>VERITAS feedback study live monitor</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#131b2d;--panel2:#182338;--line:#263550;--text:#e6edf7;--muted:#9eacc4;--blue:#69a9ff;--green:#4bd3a5;--orange:#ffbd69;--red:#ff7777;--purple:#c19aff}
*{box-sizing:border-box}body{margin:0;padding:24px;background:radial-gradient(ellipse at 10% 0%,#172542 0,transparent 42%),var(--bg);color:var(--text);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1500px;margin:auto}.top{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:20px}.title{font-size:25px;font-weight:750;letter-spacing:-.03em}.sub,.muted{color:var(--muted)}.status{border:1px solid #2d8068;color:var(--green);background:#123a32;border-radius:99px;padding:6px 11px;white-space:nowrap}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:currentColor;margin-right:7px;box-shadow:0 0 12px currentColor;animation:pulse 1.5s infinite}@keyframes pulse{50%{opacity:.35}}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:16px 0}.card,.panel{background:linear-gradient(150deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:13px;padding:16px;box-shadow:0 10px 24px #0002}.label{text-transform:uppercase;letter-spacing:.08em;font-size:11px;font-weight:700;color:var(--muted)}.value{font-size:25px;font-weight:750;margin:6px 0 2px;font-variant-numeric:tabular-nums}.small{font-size:12px;color:var(--muted)}.bar{height:7px;background:#26334a;border-radius:99px;overflow:hidden;margin-top:10px}.bar>i{display:block;height:100%;background:linear-gradient(90deg,var(--blue),var(--green));border-radius:99px;transition:width .4s}.cols{display:grid;grid-template-columns:1.1fr .9fr;gap:12px;margin:12px 0}.phase{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:12px;margin-top:14px}.phasebox{background:#0c1424;border:1px solid var(--line);border-radius:10px;padding:14px}.phasebox b{display:block;font-size:19px;margin:4px 0}.arrow{font-size:22px;color:var(--blue)}h2{font-size:16px;margin:0 0 12px}.pair{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.pair div{background:#0c1424;border-radius:9px;padding:12px}.pair strong{display:block;font-size:20px}.tablewrap{overflow:auto}table{border-collapse:collapse;width:100%;min-width:900px}th,td{text-align:left;padding:10px 9px;border-bottom:1px solid var(--line);font-size:12px;white-space:nowrap}th{color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-size:10px}td:first-child{font-weight:700;color:var(--blue)}.tag{padding:3px 7px;border-radius:5px;background:#26334a}.arm-adaptive{color:var(--purple)!important}.terminal{background:#070b12;border:1px solid var(--line);border-radius:9px;padding:12px;max-height:300px;overflow:auto;white-space:pre-wrap;font:11px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace;color:#b4efc8}.foot{font-size:11px;color:var(--muted);margin:14px 2px}.livegrid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}.livegrid .phasebox{min-height:75px}@media(max-width:850px){body{padding:13px}.cols{grid-template-columns:1fr}.pair{grid-template-columns:repeat(2,1fr)}.phase{grid-template-columns:1fr}.arrow{transform:rotate(90deg);text-align:center}}
</style></head><body><main class="wrap">
<header class="top"><div><div class="title" id="title">VERITAS Feedback Study · Live Monitor</div><div class="sub" id="subtitle">Connecting to study files…</div></div><div class="status"><i class="dot"></i><span id="live-status">POLLING LIVE FILES</span></div></header>
<section class="cards">
 <article class="card"><div class="label">Task progress</div><div class="value" id="progress">0 / 0</div><div class="bar"><i id="progressbar" style="width:0%"></i></div><div class="small" id="branchprogress">0 / 0 branches recorded</div></article>
 <article class="card"><div class="label">Parent drafts graded</div><div class="value" id="parents">0 / 0</div><div class="small" id="parentrate">Correct before feedback: —</div></article>
 <article class="card"><div class="label">Primary paired sample</div><div class="value" id="pairedn">0</div><div class="small">Initially incorrect parents with both comparison arms graded</div></article>
 <article class="card"><div class="label">Total actor tokens</div><div class="value" id="alltokens">0</div><div class="small" id="tokenquality">Prompt + completion tokens</div></article>
 <article class="card"><div class="label">Current task</div><div class="value" style="font-size:15px;overflow-wrap:anywhere" id="task">Waiting for run log</div><div class="small" id="repo">—</div></article>
 <article class="card"><div class="label">Current arm</div><div class="value" style="font-size:18px" id="arm">Waiting</div><div class="small" id="partition">—</div></article>
</section>
<section class="cols"><article class="panel"><h2>Token use before and after feedback</h2><div class="phase"><div class="phasebox"><span class="label">Before verifier · shared draft</span><b id="drafttokens">0 tokens</b><span class="small" id="draftdetail">Prompt 0 · completion 0 · 0 calls</span></div><div class="arrow">→</div><div class="phasebox"><span class="label">After verifier · all continuations</span><b id="revisiontokens">0 tokens</b><span class="small" id="revisiondetail">Prompt 0 · completion 0</span></div></div><div class="foot">Draft is shared once per task; continuation tokens are counted separately for each of five arms. Draft credit is a token-only estimate; revision credits use the runner's formula. Missing usage is not imputed.</div></article>
<article class="panel"><h2>Adaptive vs fixed actionable</h2><div class="pair"><div><span class="small">Paired n</span><strong id="pairn">0</strong></div><div><span class="small">Adaptive only</span><strong id="adaptiveonly">0</strong></div><div><span class="small">Fixed only</span><strong id="fixedonly">0</strong></div><div><span class="small">Tied</span><strong id="tied">0</strong></div></div><div class="foot" id="pairrate">Recovery: adaptive — · fixed actionable —</div></article></section>
<section class="panel"><h2>Per-arm outcome and efficiency</h2><div class="tablewrap"><table><thead><tr><th>Arm</th><th>Recorded</th><th>Resolved</th><th>Resolution</th><th>Recovery from incorrect</th><th>Recovery / 1k tokens</th><th>Regressions</th><th>Revision tokens</th><th>Mean tokens / branch</th><th>Mean credits*</th><th>Credits / recovery*</th><th>Mean checkpoints</th><th>Mean seconds</th><th>Infra errors</th></tr></thead><tbody id="armrows"><tr><td colspan="14" class="muted">Waiting for results…</td></tr></tbody></table></div><div class="foot">* Runner-estimated credits; the configured reference budget is not enforced. Efficiency values are descriptive; parent-correct tasks and unrecorded tasks affect their interpretation.</div></section>
<section class="cols"><article class="panel"><h2>Recent completed branches</h2><div class="tablewrap"><table><thead><tr><th>Task</th><th>Arm</th><th>Parent</th><th>Final</th><th>Revision tokens</th><th>Credits*</th><th>Time</th><th>Grader</th></tr></thead><tbody id="recent"><tr><td colspan="8" class="muted">Waiting for completed branches…</td></tr></tbody></table></div></article>
<article class="panel"><h2>Live executor log</h2><div class="terminal" id="log">Waiting for run.log…</div></article></section>
<section class="panel"><h2>Interpretation and data quality</h2><div class="livegrid"><div class="phasebox"><span class="label">Incorrect parent blocks</span><b id="incorrect">0</b><span class="small">Only these contribute to the primary recovery comparison.</span></div><div class="phasebox"><span class="label">Completion usage</span><b id="usagecoverage">—</b><span class="small">Arms reporting complete token counts.</span></div><div class="phasebox"><span class="label">Study status</span><b id="studywarning" style="font-size:14px">Descriptive pilot</b><span class="small">This dashboard does not perform repository-clustered inference.</span></div></div><div class="foot">This live view is an operational monitor for the paper pilot. Preserve the frozen plan, execution protocol, result ledger, parent/branch grades, event ledgers, and final analysis as the reproducibility record.</div></section>
<div class="foot" id="updated">Updating every 2 seconds</div></main>
<script>
const nfmt=n=>n==null?'—':Number(n).toLocaleString();
const pct=(n,d)=>d?`${(100*n/d).toFixed(1)}%`:'—';
const safe=s=>String(s??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function refresh(){try{const r=await fetch('/api/stats',{cache:'no-store'});const d=await r.json();
document.getElementById('title').textContent=d.benchmark_title;document.getElementById('subtitle').textContent=d.benchmark_subtitle;
document.getElementById('progress').textContent=`${d.completed_blocks} / ${d.total_blocks}`;const p=d.total_blocks?100*d.completed_blocks/d.total_blocks:0;document.getElementById('progressbar').style.width=`${p}%`;
document.getElementById('branchprogress').textContent=`${nfmt(d.completed_branches)} / ${nfmt(d.total_branches)} branches recorded`;
document.getElementById('parents').textContent=`${d.graded_parents} / ${d.total_blocks}`;document.getElementById('parentrate').textContent=`Resolved before feedback: ${d.parent_resolution_rate==null?'—':d.parent_resolution_rate+'%'} · incorrect: ${d.parent_incorrect}`;
document.getElementById('pairedn').textContent=nfmt(d.paired.n);document.getElementById('alltokens').textContent=nfmt(d.all_actor_tokens);document.getElementById('tokenquality').textContent=`${nfmt(d.draft.tokens)} draft + ${nfmt(d.revision.tokens)} continuation tokens`;
document.getElementById('task').textContent=d.active.task||d.last_task||'Waiting';document.getElementById('repo').textContent=d.active.repository||d.last_repo||'—';document.getElementById('arm').textContent=d.active.arm||d.last_arm||'Starting / between arms';document.getElementById('partition').textContent=d.active.partition?`Block ${d.active.index}/${d.active.total} · ${d.active.partition}`:'Current execution state from run.log';
document.getElementById('drafttokens').textContent=`${nfmt(d.draft.tokens)} tokens`;document.getElementById('draftdetail').textContent=`Prompt ${nfmt(d.draft.prompt_tokens)} · completion ${nfmt(d.draft.completion_tokens)} · ${d.draft.steps} calls · token credit est. ${d.draft.token_credit_estimate}`;
document.getElementById('revisiontokens').textContent=`${nfmt(d.revision.tokens)} tokens`;document.getElementById('revisiondetail').textContent=`Prompt ${nfmt(d.revision.prompt_tokens)} · completion ${nfmt(d.revision.completion_tokens)} · reported credits ${d.revision.reported_estimated_credits}`;
document.getElementById('pairn').textContent=nfmt(d.paired.n);document.getElementById('adaptiveonly').textContent=nfmt(d.paired.adaptive_only);document.getElementById('fixedonly').textContent=nfmt(d.paired.fixed_only);document.getElementById('tied').textContent=nfmt(d.paired.both_or_neither);
document.getElementById('pairrate').textContent=`Recovery among incorrect parents: adaptive ${pct(d.paired.adaptive_recovered,d.paired.n)} (${d.paired.adaptive_recovered}/${d.paired.n}) · fixed actionable ${pct(d.paired.fixed_recovered,d.paired.n)} (${d.paired.fixed_recovered}/${d.paired.n})`;
document.getElementById('incorrect').textContent=nfmt(d.parent_incorrect);let usable=d.arm_stats.reduce((a,x)=>a+x.usage_complete,0),arms=d.arm_stats.reduce((a,x)=>a+x.count,0);document.getElementById('usagecoverage').textContent=arms?`${usable}/${arms} (${pct(usable,arms)})`:'—';
const rows=document.getElementById('armrows');rows.innerHTML='';for(const a of d.arm_stats){const tr=document.createElement('tr');if(a.arm==='adaptive')tr.className='arm-adaptive';tr.innerHTML=`<td>${safe(a.arm)}</td><td>${a.count}</td><td>${a.resolved}/${a.graded}</td><td>${a.resolution_rate==null?'—':a.resolution_rate+'%'}</td><td>${a.recovery_resolved}/${a.recovery_total}</td><td>${a.recoveries_per_1k_tokens??'—'}</td><td>${a.regressions}/${a.regression_total}</td><td>${nfmt(a.tokens)}</td><td>${nfmt(a.mean_tokens)}</td><td>${a.mean_credits??'—'}</td><td>${a.credits_per_recovery??'—'}</td><td>${a.mean_checkpoints??'—'}</td><td>${a.mean_seconds??'—'}</td><td>${a.infrastructure_errors}</td>`;rows.appendChild(tr)}
const recent=document.getElementById('recent');recent.innerHTML='';for(const x of d.recent_records.slice().reverse()){const tr=document.createElement('tr');tr.innerHTML=`<td>${safe(x.task_id)}</td><td>${safe(x.arm)}</td><td>${x.parent_resolved==null?'—':x.parent_resolved?'resolved':'incorrect'}</td><td>${x.resolved==null?'unknown':x.resolved?'resolved':'unresolved'}</td><td>${nfmt((x.actor_prompt_tokens||0)+(x.actor_completion_tokens||0))}</td><td>${x.total_credits??'—'}</td><td>${x.wall_seconds??'—'} s</td><td>${safe(x.grader_status)}</td>`;recent.appendChild(tr)}
document.getElementById('log').textContent=d.live_log_tail||'Waiting for run.log…';document.getElementById('updated').textContent=`Last refreshed ${new Date().toLocaleTimeString()} · auto-refresh 2s`;document.getElementById('live-status').textContent=d.completed_branches>=d.total_branches&&d.total_branches?'RUN COMPLETE':'LIVE FILE POLLING';
}catch(e){document.getElementById('live-status').textContent='WAITING FOR STUDY FILES';document.getElementById('log').textContent=String(e)}}setInterval(refresh,2000);refresh();
</script></body></html>"""


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/stats":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            stats = get_stats()
            self.wfile.write(json.dumps(stats).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            template = FEEDBACK_HTML_TEMPLATE if os.environ.get("FEEDBACK_STUDY_DIR") else HTML_TEMPLATE
            self.wfile.write(template.encode("utf-8"))

    def log_message(self, format, *args):
        pass


def run_dashboard():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), DashboardHandler) as httpd:
        print(f"Live dashboard serving on http://localhost:{PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    run_dashboard()
