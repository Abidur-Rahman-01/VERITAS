import json
from pathlib import Path
from veritas.data import load_tasks
from veritas.labels import grade_answer, numeric_answer

tasks = {task.task_id: task for task, _ in load_tasks("data/prepared")}

queue_path = Path("artifacts/annotation-queue.jsonl")
output_path = Path("artifacts/annotations.jsonl")

annotated = []
for line in queue_path.read_text().splitlines():
    if not line.strip():
        continue
    row = json.loads(line)
    task = tasks.get(row["task_id"])
    if not task:
        continue
    tool = row["action"]["proposal"]["tool"]
    obs = row["observation"]
    content = obs.get("content", "")
    
    # Try parsing observation content
    try:
        obs_data = json.loads(content) if isinstance(content, str) else content
    except Exception:
        obs_data = {}

    if tool == "final_answer":
        ans = row["action"]["proposal"]["args"].get("answer", "")
        correct = grade_answer(task, ans)
        row["error_label"] = 0 if correct else 1
        row["label_scope"] = "semantic"
        row["label_source"] = "official_ground_truth_numeric_match" if correct else "official_ground_truth_numeric_mismatch"
    elif tool == "python":
        exit_code = obs_data.get("exit_code", 0) if isinstance(obs_data, dict) else 0
        output_val = obs_data.get("output", "").strip() if isinstance(obs_data, dict) else ""
        expected = numeric_answer(task.private.get("answer", ""))
        actual = numeric_answer(output_val)
        if exit_code != 0:
            row["error_label"] = 1
            row["label_scope"] = "semantic"
            row["label_source"] = "python_execution_runtime_error"
        elif actual is not None and expected is not None and actual == expected:
            row["error_label"] = 0
            row["label_scope"] = "semantic"
            row["label_source"] = "sound_computation_matching_ground_truth"
        elif actual is not None and expected is not None and actual != expected:
            row["error_label"] = 1
            row["label_scope"] = "semantic"
            row["label_source"] = "computation_mismatch_with_ground_truth"
        else:
            row["error_label"] = 0 if exit_code == 0 else 1
            row["label_scope"] = "semantic"
            row["label_source"] = "intermediate_step_execution_success" if exit_code == 0 else "intermediate_step_failure"
            
    annotated.append(row)

output_path.write_text("\n".join(json.dumps(r) for r in annotated) + "\n")
print(f"Annotated {len(annotated)} actions successfully.")
