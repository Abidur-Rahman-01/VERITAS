from pathlib import Path
import json

blocks_dir = Path("runs/feedback_study_v2_500/blocks")
block_dirs = [p for p in blocks_dir.iterdir() if p.is_dir()]
print(f"Total block dirs: {len(block_dirs)}")

for b in block_dirs:
    print(f"\n=== Block: {b.name}")
    pg_file = b / "parent_grade.json"
    if pg_file.exists():
        pg = json.loads(pg_file.read_text(encoding="utf-8"))
        print(f"  Parent resolved: {pg.get('parent_resolved')}")
        print(f"  Parent grade output snippet: {pg.get('output', '')[:200]}")
    
    pp_file = b / "parent.patch"
    if pp_file.exists():
        patch_text = pp_file.read_text(encoding="utf-8")
        print(f"  Parent patch len: {len(patch_text)}")
        if patch_text:
            print(f"  Parent patch snippet: {patch_text[:200]}")
    
    ps_file = b / "parent_session.json"
    if ps_file.exists():
        ps = json.loads(ps_file.read_text(encoding="utf-8"))
        print(f"  Parent session steps: {ps.get('step')}")
        for i, h in enumerate(ps.get("history", [])):
            role = h.get("role")
            content = h.get("content", "")
            print(f"    History [{i}] {role}: {content[:150]!r}")
            if "tool_calls" in h:
                print(f"      tool_calls: {h['tool_calls']}")

    for arm in ["generic_retry", "fixed_actionable", "adaptive"]:
        arm_dir = b / arm
        if arm_dir.exists():
            final_patch = arm_dir / "final.patch"
            fp_len = len(final_patch.read_text(encoding="utf-8")) if final_patch.exists() else 0
            grade_file = arm_dir / "grade.json"
            g = json.loads(grade_file.read_text(encoding="utf-8")) if grade_file.exists() else {}
            print(f"  [{arm}] resolved={g.get('resolved')} steps={g.get('steps')} final_patch_len={fp_len}")
            events_file = arm_dir / "events.jsonl"
            if events_file.exists():
                lines = events_file.read_text(encoding="utf-8").splitlines()
                print(f"    events count: {len(lines)}")
