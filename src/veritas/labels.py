from decimal import Decimal, InvalidOperation

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
