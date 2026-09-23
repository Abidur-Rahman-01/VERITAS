"""Standard-library-only worker copied into a disposable container; never run on the host."""

import json
import os
import subprocess
import sys
from pathlib import Path


def path(value):
    root = Path.cwd().resolve()
    target = (root / value).resolve()
    if root != target and root not in target.parents:
        raise ValueError("Path outside sandbox workspace")
    return target


def execute(proposal):
    tool, args = proposal["tool"], proposal["args"]
    if tool == "list_files":
        target = path(args["path"])
        return "\n".join(
            sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir())[: args["limit"]]
        )
    if tool == "read_file":
        with path(args["path"]).open(errors="replace") as f:
            lines = []
            for n, line in enumerate(f, 1):
                if n >= args["start_line"]:
                    lines.append(f"{n}: {line}")
                if len(lines) >= args["max_lines"]:
                    break
        return "".join(lines)
    if tool == "write_file":
        target = path(args["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(args["content"])
        return "File written"
    if tool == "delete_file":
        path(args["path"]).unlink()
        return "File deleted"
    if tool == "sql":
        import sqlite3

        with sqlite3.connect(path(args["database"])) as db:
            db.enable_load_extension(False)

            def authorize(action, *_):
                return (
                    sqlite3.SQLITE_DENY
                    if action in {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH}
                    else sqlite3.SQLITE_OK
                )

            db.set_authorizer(authorize)
            cursor = db.execute(args["query"], args["parameters"])
            return (
                json.dumps(cursor.fetchmany(1000))
                if cursor.description
                else f"Rows changed: {cursor.rowcount}"
            )
    if tool in {"python", "run_tests"}:
        argv = [sys.executable, "-c", args["code"]] if tool == "python" else args["argv"]
        # Child stdout stays in the container; host reads at most max_output bytes.
        with open("/tmp/veritas-child.log", "wb") as log:
            result = subprocess.run(
                argv,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=int(os.environ.get("VERITAS_TIMEOUT", "55")),
                check=False,
            )
        with open("/tmp/veritas-child.log", "rb") as log:
            text = log.read(16000).decode(errors="replace")
        return {"exit_code": result.returncode, "output": text}
    raise ValueError("Unsupported worker action")


if __name__ == "__main__":
    try:
        value = execute(json.loads(sys.stdin.read()))
        print(json.dumps(value if isinstance(value, dict) else {"exit_code": 0, "output": value}))
    except Exception as e:
        print(json.dumps({"exit_code": 1, "output": f"{type(e).__name__}: {e}"}))
