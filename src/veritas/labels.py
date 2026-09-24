from decimal import Decimal, InvalidOperation
from pathlib import Path

from .io import read_records, write_jsonl


def numeric_answer(value):
    value = value.strip().split("####")[-1].strip().replace(",", "")
    if value.startswith("\\boxed{") and value.endswith("}"):
        value = value[7:-1].strip()
    try:
        answer = Decimal(value)
        return answer if answer.is_finite() else None
    except InvalidOperation:
        return None


def grade_answer(task, answer):
    if task.kind == "gsm8k":
        expected = numeric_answer(task.private["answer"])
        actual = numeric_answer(answer)
        return actual is not None and expected is not None and actual == expected
    if task.kind == "math":
        # Exact normalized string metric only; symbolic equivalence needs expert adjudication.
        def normalize(s):
            s = "".join(s.strip().split())
            return s[7:-1] if s.startswith("\\boxed{") and s.endswith("}") else s

        return normalize(answer) == normalize(task.private["answer"])
    return None


def annotation_queue(records, output):
    def rows():
        for row in read_records(records):
            if not row.get("blocked"):
                # Hide verifier verdict and critic score to reduce adjudicator confirmation bias.
                yield {
                    "event_id": row["event_id"],
                    "task_id": row["task_id"],
                    "context": row["context"],
                    "action": row["action"],
                    "observation": row["observation"],
                    "error_label": None,
                    "label_scope": "semantic",
                    "label_source": None,
                }

    write_jsonl(output, rows())


def annotate_math_queue(queue, tasks_dir, output):
    """Label final submissions only; intermediate computations need independent review."""
    from .data import load_tasks

    if Path(output).exists():
        raise ValueError("Annotation output exists; choose a new filename to preserve evidence")
    tasks = {task.task_id: task for task, _ in load_tasks(tasks_dir)}
    counts = {"total": 0, "semantic_labeled": 0, "needs_review": 0}
    seen = set()

    def rows():
        for original in read_records(queue):
            row = dict(original)
            if row["event_id"] in seen:
                raise ValueError("Duplicate event ID in annotation queue")
            seen.add(row["event_id"])
            task = tasks.get(row["task_id"])
            if task is None:
                raise ValueError(f"Annotation task missing from prepared data: {row['task_id']}")
            row.update(error_label=None, label_scope="unknown", label_source=None)
            row["annotation_note"] = "Intermediate action requires independent semantic review."
            proposal = (row.get("action") or {}).get("proposal", {})
            if proposal.get("tool") == "final_answer":
                answer = proposal.get("args", {}).get("answer")
                if task.kind == "gsm8k" and isinstance(answer, str):
                    if numeric_answer(task.private["answer"]) is None:
                        raise ValueError("Invalid GSM8K reference answer; do not fabricate a label")
                    correct = grade_answer(task, answer)
                    row.update(
                        error_label=int(not correct),
                        label_scope="semantic",
                        label_source="official_numeric_answer",
                        annotation_note="Final submission graded against original numeric reference.",
                    )
                elif task.kind == "math" and isinstance(answer, str):
                    if grade_answer(task, answer):
                        row.update(
                            error_label=0,
                            label_scope="semantic",
                            label_source="official_exact_string_answer",
                            annotation_note="Final submission matches the original reference string.",
                        )
                    else:
                        row["annotation_note"] = (
                            "Exact mismatch requires mathematical equivalence review."
                        )
                else:
                    row["annotation_note"] = (
                        "No independent final-answer grader for this annotation."
                    )
            counts["total"] += 1
            counts["semantic_labeled" if row["error_label"] is not None else "needs_review"] += 1
            yield row

    write_jsonl(output, rows())
    return counts


def apply_annotations(records, annotations, output):
    from .schema import StepRecord

    labels = {}
    for row in read_records(annotations):
        if row["event_id"] in labels:
            raise ValueError("Duplicate annotation event_id")
        if row.get("error_label") is None:
            continue
        if row["error_label"] not in [0, 1] or not row.get("label_source"):
            raise ValueError(
                "Annotations need binary error_label and independent evidence in label_source"
            )
        labels[row["event_id"]] = row
    matched = set()

    def rows():
        for row in read_records(records):
            if row["event_id"] in labels:
                label = labels[row["event_id"]]
                row.update({k: label[k] for k in ("error_label", "label_scope", "label_source")})
                matched.add(row["event_id"])
            yield StepRecord.model_validate(row).model_dump(mode="json")
        if matched != set(labels):
            raise ValueError("Annotations include unknown event IDs")

    write_jsonl(output, rows())
