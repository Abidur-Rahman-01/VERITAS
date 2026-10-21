import json
from pathlib import Path

results_file = Path("runs/feedback_study_full/results.jsonl")
results = [json.loads(line) for line in results_file.read_text(encoding="utf-8").splitlines() if line.strip()]
failed_blocks = [r for r in results if r["parent_resolved"] is False and r["arm"] == "adaptive"]
print(f"Total failed parent blocks: {len(failed_blocks)}")

for sample in failed_blocks[:3]:
    block_id = sample["block_id"]
    task_id = sample["task_id"]
    print(f"\n=======================================================")
    print(f"Block {block_id} | Task: {task_id}")
    print(f"=======================================================")

    block_dir = Path("runs/feedback_study_full/blocks") / block_id
    parent_grade = json.loads((block_dir / "parent_grade.json").read_text(encoding="utf-8"))
    print(f"Parent Pytest Output (Why parent draft failed):\n{parent_grade['output'].strip()[:400]}")

    parent_sess = json.loads((block_dir / "parent_session.json").read_text(encoding="utf-8"))
    print(f"\nParent draft history ({len(parent_sess.get('history', []))} steps):")
    for i, h in enumerate(parent_sess.get("history", [])):
        action = h.get("action")
        tool = action.get("tool") if isinstance(action, dict) else str(action)
        args = action.get("args") if isinstance(action, dict) else {}
        print(f"  Step {i}: tool={tool} args={args}")

    # Inspect branch execution in adaptive and fixed_actionable
    for arm in ["fixed_actionable", "adaptive"]:
        arm_dir = block_dir / arm
        if (arm_dir / "grade.json").exists():
            grade = json.loads((arm_dir / "grade.json").read_text(encoding="utf-8"))
            print(f"\nArm {arm} final grade: resolved={grade.get('resolved')} steps={grade.get('steps')}")
            print(f"Final patch content:")
            patch_file = arm_dir / "final.patch"
            if patch_file.exists():
                print(patch_file.read_text(encoding="utf-8")[:300])

        events_file = arm_dir / "events.jsonl"
        if events_file.exists():
            evs = [json.loads(l) for l in events_file.read_text(encoding="utf-8").splitlines() if l.strip()]
            print(f"Arm {arm} events ({len(evs)} checkpoints):")
            for idx, ev in enumerate(evs[:3]):
                dec = ev.get("decision", {})
                print(f"  CP {idx}: arm={dec.get('arm')} packet_preview=\n{dec.get('packet', '')[:250]}")
