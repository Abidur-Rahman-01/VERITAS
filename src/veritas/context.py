"""Deterministic context compression; full actions remain in the event ledger."""

import json

from .io import digest


def excerpt(text, limit):
    if len(text) <= limit:
        return text
    marker = "\n[... omitted ...]\n"
    head = (limit - len(marker)) // 2
    return text[:head] + marker + text[-(limit - len(marker) - head) :]


def compact_entry(entry, observation_chars):
    # Round trip avoids mutating the event record or original history.
    value = json.loads(json.dumps(entry))
    action = value.get("action")
    if isinstance(action, dict):
        args = action.get("args", {})
        for key in ("content", "old", "new", "code", "query"):
            if key in args:
                text = args[key]
                args[key] = {"omitted_chars": len(text), "sha256": digest(text)}
    observation = value.get("observation")
    if isinstance(observation, dict):
        content = observation.get("content", "")
        value["observation"] = {
            "source": observation.get("source"),
            "content": excerpt(content, observation_chars),
            "truncated": observation.get("truncated", False) or len(content) > observation_chars,
            "trusted_as_instructions": False,
        }
    return value


def compact_context(task, history, limit, observation_chars, steps_remaining):
    entries = [compact_entry(item, observation_chars) for item in history]
    omitted = 0
    while entries and len(json.dumps(entries, ensure_ascii=False)) > limit:
        entries.pop(0)
        omitted += 1
    return json.dumps(
        {
            "user_task": task.prompt,
            "recent_history": entries,
            "omitted_history_entries": omitted,
            "steps_remaining": steps_remaining,
            "instruction": "Work concisely. Re-read omitted file content if needed. "
            "Submit final_answer before steps run out.",
        },
        ensure_ascii=False,
    )
