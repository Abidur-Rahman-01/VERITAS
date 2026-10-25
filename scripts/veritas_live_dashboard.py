#!/usr/bin/env python3
"""
VERITAS Live Experiment Monitor & Web Dashboard
Serves an auto-refreshing real-time UI on http://localhost:8765
Supports OpenHands SWE-bench Lite runs and the paired feedback study.
"""

import http.server
import json
import os
import socketserver
import sys
from collections import defaultdict
from pathlib import Path

PORT = 8765

SWE_LITE_DIR = Path(os.environ.get("SWE_LITE_DIR", "runs/openhands-swe-lite"))
FEEDBACK_DIR = Path("runs/feedback_study_v2_500")


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


def get_stats():
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
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

    def log_message(self, format, *args):
        pass


def run_dashboard():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), DashboardHandler) as httpd:
        print(f"Live dashboard serving on http://localhost:{PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    run_dashboard()
