"""Agent tools (OpenHands/SWE-agent style) and tool-call parsing.

The tool names and editor sub-commands follow the ``execute_bash`` / ``str_replace_editor`` /
``finish`` convention used to train most open SWE agents, so agent-tuned actors see the format
they were trained on.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field

from .sandbox import Sandbox, SandboxError
from .util import truncate_middle

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_bash",
            "description": "Run a bash command in the repository root. No network access. "
            "Long output is truncated.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "The command."}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "str_replace_editor",
            "description": "View, create and edit files. `view` shows a file with line numbers "
            "or lists a directory. `create` writes a new file. `str_replace` replaces `old_str`, "
            "which must occur exactly once, with `new_str`. `insert` adds `new_str` after line "
            "`insert_line` (0 inserts at the top).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": ["view", "create", "str_replace", "insert"],
                    },
                    "path": {"type": "string"},
                    "file_text": {"type": "string"},
                    "old_str": {"type": "string"},
                    "new_str": {"type": "string"},
                    "insert_line": {"type": "integer"},
                    "view_range": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["command", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Submit the current repository state as the final fix.",
            "parameters": {"type": "object", "properties": {"message": {"type": "string"}}},
        },
    },
]
TOOL_NAMES = {t["function"]["name"] for t in TOOLS}
EDIT_COMMANDS = {"create", "str_replace", "insert"}


@dataclass
class ToolCall:
    name: str
    arguments: dict
    call_id: str = ""

    def to_message(self) -> dict:
        return {
            "id": self.call_id,
            "type": "function",
            "function": {"name": self.name, "arguments": json.dumps(self.arguments)},
        }

    @property
    def is_edit(self) -> bool:
        return self.name == "str_replace_editor" and self.arguments.get("command") in EDIT_COMMANDS


@dataclass
class ParseResult:
    calls: list[ToolCall] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


_TAGGED = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
_FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
# Qwen3-Coder format: <function=NAME><parameter=KEY>\nVALUE\n</parameter>...</function>
_XML_FUNCTION = re.compile(r"^<function=([^>\s]+)>(.*?)</function>$", re.DOTALL)
_XML_PARAMETER = re.compile(r"<parameter=([^>\s]+)>(.*?)</parameter>", re.DOTALL)
_SCHEMAS = {t["function"]["name"]: t["function"]["parameters"]["properties"] for t in TOOLS}


def _xml_call(block: str) -> dict:
    """Parse one Qwen3-Coder XML tool call into {"name", "arguments"}.

    Values are raw text; the template wraps each in exactly one leading and trailing newline,
    which are removed (inner whitespace is significant for ``old_str``). Integer and array
    parameters are converted using the tool schema, as Qwen's reference parser does.
    """
    match = _XML_FUNCTION.match(block)
    if not match:
        raise ValueError("malformed <function=...> block")
    name, body = match.group(1), match.group(2)
    schema = _SCHEMAS.get(name, {})
    arguments: dict = {}
    for key, raw in _XML_PARAMETER.findall(body):
        value = raw[1:] if raw.startswith("\n") else raw
        value = value[:-1] if value.endswith("\n") else value
        kind = schema.get(key, {}).get("type")
        if kind == "integer":
            arguments[key] = int(value.strip())
        elif kind == "array":
            arguments[key] = json.loads(value)
        else:
            arguments[key] = value
    return {"name": name, "arguments": arguments}


def _coerce(obj) -> ToolCall:
    if not isinstance(obj, dict):
        raise ValueError("tool call must be a JSON object")
    name = obj.get("name") or (obj.get("function") or {}).get("name")
    args = obj.get("arguments", obj.get("parameters"))
    if args is None and isinstance(obj.get("function"), dict):
        args = obj["function"].get("arguments")
    if isinstance(args, str):
        args = json.loads(args) if args.strip() else {}
    if args is None:
        args = {}
    if name not in TOOL_NAMES:
        raise ValueError(f"unknown tool: {name!r}")
    if not isinstance(args, dict):
        raise ValueError("tool arguments must be an object")
    return ToolCall(name=name, arguments=args)


def parse_tool_calls(text: str) -> ParseResult:
    """Extract tool calls from raw model text: ``<tool_call>`` tags holding JSON (Qwen3, Hermes)
    or ``<function=...>`` XML (Qwen3-Coder), else fenced JSON."""
    result = ParseResult()
    blocks = _TAGGED.findall(text) or _FENCED.findall(text)
    for block in blocks:
        try:
            raw = _xml_call(block) if block.startswith("<function=") else json.loads(block)
            result.calls.append(_coerce(raw))
        except (ValueError, json.JSONDecodeError) as exc:
            result.errors.append(f"could not parse tool call: {exc}")
    for i, call in enumerate(result.calls):
        call.call_id = call.call_id or f"call_{i}"
    return result


def coerce_structured(tool_calls: list[dict]) -> ParseResult:
    """Parse OpenAI-style structured ``tool_calls`` returned by a server."""
    result = ParseResult()
    for i, raw in enumerate(tool_calls):
        try:
            call = _coerce(raw)
            call.call_id = raw.get("id") or f"call_{i}"
            result.calls.append(call)
        except (ValueError, json.JSONDecodeError) as exc:
            result.errors.append(f"could not parse tool call: {exc}")
    return result


def _numbered(text: str, start: int = 1) -> str:
    return "\n".join(f"{start + i:6d}\t{line}" for i, line in enumerate(text.split("\n")))


def execute(sandbox: Sandbox, call: ToolCall, max_chars: int) -> str:
    """Run one tool call; every failure becomes an observation the agent can read."""
    try:
        if call.name == "execute_bash":
            command = str(call.arguments.get("command", ""))
            if not command.strip():
                return "ERROR: empty command"
            result = sandbox.exec(command)
            status = "TIMED OUT" if result.timed_out else f"exit code {result.exit_code}"
            return truncate_middle(f"[{status}]\n{result.output}", max_chars)
        if call.name == "finish":
            return "Submitted."
        return truncate_middle(_editor(sandbox, call.arguments), max_chars)
    except SandboxError as exc:
        return f"ERROR: {exc}"


def _editor(sandbox: Sandbox, args: dict) -> str:
    command = args.get("command")
    path = sandbox.relpath(str(args.get("path", "")))
    if command == "view":
        content = sandbox.read_file(path) if path else None
        if content is None:
            listing = sandbox.exec(
                f"find {shlex.quote(path or '.')} -maxdepth 2 -not -path '*/.*' | sort | head -300"
            )
            if listing.exit_code != 0 or not listing.output.strip():
                return f"ERROR: {path or '.'} does not exist"
            return listing.output
        lines = content.split("\n")
        view_range = args.get("view_range")
        if view_range:
            if (not isinstance(view_range, list) or len(view_range) != 2
                    or not all(isinstance(v, int) for v in view_range)):
                return "ERROR: view_range must be [start, end]"
            start, end = view_range
            end = len(lines) if end == -1 else end
            if start < 1 or end < start:
                return "ERROR: invalid view_range"
            return _numbered("\n".join(lines[start - 1:end]), start)
        return _numbered(content)
    if command == "create":
        if "file_text" not in args:
            return "ERROR: create requires file_text"
        if sandbox.read_file(path) is not None:
            return f"ERROR: {path} already exists; use str_replace to edit it"
        sandbox.write_file(path, str(args["file_text"]))
        return f"File created: {path}"
    if command == "str_replace":
        content = sandbox.read_file(path)
        if content is None:
            return f"ERROR: {path} does not exist"
        old, new = args.get("old_str"), args.get("new_str", "")
        if not isinstance(old, str) or old == "":
            return "ERROR: str_replace requires a non-empty old_str"
        count = content.count(old)
        if count != 1:
            return f"ERROR: old_str occurs {count} times in {path}; it must occur exactly once"
        sandbox.write_file(path, content.replace(old, str(new), 1))
        return f"Edited {path}"
    if command == "insert":
        content = sandbox.read_file(path)
        if content is None:
            return f"ERROR: {path} does not exist"
        line = args.get("insert_line")
        lines = content.split("\n")
        if not isinstance(line, int) or not 0 <= line <= len(lines):
            return f"ERROR: insert_line must be between 0 and {len(lines)}"
        lines[line:line] = str(args.get("new_str", "")).split("\n")
        sandbox.write_file(path, "\n".join(lines))
        return f"Inserted into {path} after line {line}"
    return f"ERROR: unknown editor command {command!r}"
