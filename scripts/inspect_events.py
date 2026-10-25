from pathlib import Path
import json
import sqlite3

for b in sorted(Path("runs/feedback_study_v2_500/blocks").iterdir()):
    if not b.is_dir():
        continue
    db_file = b / "draft_events.sqlite"
    if db_file.exists():
        print(f"\n==========================================")
        print(f"=== Block: {b.name}")
        conn = sqlite3.connect(db_file)
        rows = conn.execute("SELECT seq, payload FROM events ORDER BY seq").fetchall()
        for seq, payload_str in rows:
            p = json.loads(payload_str) if payload_str else {}
            event_type = p.get("type") or p.get("kind") or "unknown"
            print(f"  [{seq}] Payload keys: {list(p.keys())}")
            if "proposal" in p:
                print(f"       Proposal: {p['proposal']}")
            if "error" in p:
                print(f"       Error: {p['error']}")
            if "content" in p:
                print(f"       Content: {str(p['content'])[:150]!r}")
            if "observation" in p:
                print(f"       Observation: {str(p['observation'])[:150]!r}")
        conn.close()
