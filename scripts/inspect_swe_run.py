import sqlite3
import json
import sys

def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "runs/swe-test-pilot-1/events.sqlite"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT event_id, payload FROM events ORDER BY rowid ASC")
    rows = cursor.fetchall()
    print(f"Total events: {len(rows)}")
    for i, (eid, p) in enumerate(rows):
        data = json.loads(p)
        act = data.get("action") or {}
        proposal = act.get("proposal") if isinstance(act, dict) else {}
        tool = proposal.get("tool") if isinstance(proposal, dict) else act.get("tool")
        args = proposal.get("args") if isinstance(proposal, dict) else act.get("args")
        obs = data.get("observation") or {}
        obs_content = obs.get("content") if isinstance(obs, dict) else str(obs)
        score = data.get("p_error") or data.get("critic_score")
        dec = data.get("decision")
        ver = data.get("verification")
        ver_verdict = ver.get("verdict") if isinstance(ver, dict) else None
        ver_reason = ver.get("reason") if isinstance(ver, dict) else None
        blocked = data.get("blocked")
        block_reason = data.get("block_reason")

        print(f"--- Step {i+1} [{eid[:8]}] ---")
        print(f"Action Tool: {tool}")
        if isinstance(args, dict) and "code" in args:
            code_preview = args["code"].replace("\n", " ")[:120]
            print(f"Args code: {code_preview}...")
        elif isinstance(args, dict) and "command" in args:
            print(f"Args command: {args['command']}")
        else:
            print(f"Args: {str(args)[:120]}")
        print(f"Obs: {str(obs_content)[:120]}")
        if score is not None:
            print(f"p_error: {score:.3f}")
        if dec:
            print(f"Decision: {dec}, Verifier: {ver_verdict} ({ver_reason})")
        if blocked:
            print(f"BLOCKED: {block_reason}")

if __name__ == "__main__":
    main()
