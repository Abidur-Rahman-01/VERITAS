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


def phase_context(task, history, *, phase, cue, boundary, history_chars,
                  observation_chars, compact, steps_remaining, input_chars):
    """Keep experimental notices out of the trimmable, untrusted history.

    input_chars bounds rendered characters, not tokenizer-specific tokens. Refuse an
    oversized immutable task instead of silently truncating the intervention or goal.
    """
    entries = [compact_entry(x, observation_chars) for x in history] if compact else list(history)
    value = {
        "user_task": task.prompt,
        "phase": phase,
        "workflow": "This task has a draft phase and a revision phase. Submit final_answer to "
                    "close the current phase. Both phases allow edits and tests.",
        "steps_remaining": steps_remaining,
        "recent_history": entries,
    }
    if cue:
        value["initial_session_notice"] = cue
    if boundary is not None:
        value["boundary_message"] = boundary
    while entries and len(json.dumps(entries, ensure_ascii=False)) > history_chars:
        entries.pop(0)
    while True:
        rendered = json.dumps(value, ensure_ascii=False)
        if len(rendered) <= input_chars:
            return rendered
        if not entries:
            raise ValueError("Immutable task/treatment exceeds configured input character cap")
        entries.pop(0)
