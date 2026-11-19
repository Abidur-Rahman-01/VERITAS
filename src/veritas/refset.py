"""Reference fixes in the actor's own action format (outcome plane only).

For a checkpoint whose workspace equals ``base + agent_patch``, the reference turn is the set of
editor actions that turns the *current* content of each file touched by a reference patch into
that file's content under ``base + reference_patch``. Actions are verified by simulation; if
the minimal hunks do not reproduce the target exactly, the file falls back to one whole-file
``str_replace`` (always unique), so a reference is never silently wrong.
"""

from __future__ import annotations

import difflib
import json
import subprocess
import tempfile
from pathlib import Path

from .sandbox import Sandbox
from .tasks import is_test_path, patch_files

CONTEXT = 2


class PatchError(RuntimeError):
    pass


def source_paths(patch: str) -> list[str]:
    return [p for p in patch_files(patch) if not is_test_path(p)]


def read_base_files(sandbox: Sandbox, paths: list[str]) -> dict[str, str | None]:
    """Read files from a clean base-commit workspace (None if absent at base)."""
    return {path: sandbox.read_file(path) for path in paths}


def materialize(base: dict[str, str | None], patch: str, paths: list[str]) -> dict[str, str | None]:
    """Apply ``patch`` (only its hunks for ``paths``) to the base files, on the host, with git."""
    if not patch.strip():
        return {p: base.get(p) for p in paths}
    with tempfile.TemporaryDirectory(prefix="veritas-ref-") as tmp:
        root = Path(tmp)
        for path, content in base.items():
            if content is not None:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
        (root / "change.patch").write_text(patch, encoding="utf-8")
        includes = [f"--include={p}" for p in paths]
        proc = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", *includes, "change.patch"],
            cwd=root, capture_output=True, text=True, check=False,
        )
        if proc.returncode != 0:
            raise PatchError(proc.stderr.strip()[:500])
        out: dict[str, str | None] = {}
        for path in paths:
            target = root / path
            out[path] = target.read_text(encoding="utf-8") if target.is_file() else None
        return out


def _hunk_actions(path: str, old: str, new: str) -> list[dict]:
    a = old.splitlines(keepends=True)
    b = new.splitlines(keepends=True)
    actions = []
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for group in matcher.get_grouped_opcodes(CONTEXT):
        i1, i2 = group[0][1], group[-1][2]
        j1, j2 = group[0][3], group[-1][4]
        while True:
            old_str = "".join(a[i1:i2])
            if old_str and old.count(old_str) == 1:
                break
            grew = False
            if i1 > 0 and j1 > 0:
                i1, j1, grew = i1 - 1, j1 - 1, True
            if i2 < len(a) and j2 < len(b):
                i2, j2, grew = i2 + 1, j2 + 1, True
            if not grew:
                break
        actions.append({"command": "str_replace", "path": path,
                        "old_str": "".join(a[i1:i2]), "new_str": "".join(b[j1:j2])})
    return actions


def _simulate(content: str, actions: list[dict]) -> str | None:
    for action in actions:
        old = action["old_str"]
        if not old or content.count(old) != 1:
            return None
        content = content.replace(old, action["new_str"], 1)
    return content


def edit_actions(current: dict[str, str | None], target: dict[str, str | None]) -> list[dict]:
    """Tool calls (name + arguments) turning ``current`` into ``target``, file by file."""
    calls: list[dict] = []
    for path in sorted(target):
        before, after = current.get(path), target[path]
        if before == after:
            continue
        if after is None:
            calls.append({"name": "execute_bash", "arguments": {"command": f"rm -f {path}"}})
            continue
        if before is None:
            calls.append({"name": "str_replace_editor",
                          "arguments": {"command": "create", "path": path, "file_text": after}})
            continue
        actions = _hunk_actions(path, before, after)
        if _simulate(before, actions) != after:
            actions = [{"command": "str_replace", "path": path, "old_str": before,
                        "new_str": after}]
        calls += [{"name": "str_replace_editor", "arguments": a} for a in actions]
    return calls


def reference_message(calls: list[dict], current: dict[str, str | None],
                      target: dict[str, str | None], fmt: str = "edit") -> dict:
    """The assistant turn to teacher-force. ``diff`` format is the E3 ablation.

    If the workspace already matches the reference, the correct next action is to submit, so the
    reference turn is a ``finish`` call.
    """
    if not calls:
        calls = [{"name": "finish", "arguments": {}}]
    elif fmt == "diff":
        chunks = []
        for path in sorted(target):
            before, after = current.get(path) or "", target[path] or ""
            if before != after:
                chunks += difflib.unified_diff(
                    before.splitlines(keepends=True), after.splitlines(keepends=True),
                    fromfile=f"a/{path}", tofile=f"b/{path}",
                )
        return {"role": "assistant", "content": "```diff\n" + "".join(chunks) + "```"}
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": f"ref_{i}", "type": "function",
             "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}}
            for i, c in enumerate(calls)
        ],
    }
