"""Standard-library-only worker copied into a disposable container; never run on the host."""

import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path



def path(value):
    root = Path.cwd().resolve()
    target = (root / value).resolve()
    if root != target and root not in target.parents:
        raise ValueError("Path outside sandbox workspace")
    return target


def replace_unique(text, old, new, filename):
    if not old:
        raise ValueError("edit_file old text cannot be empty")
    
    # 1. Exact verbatim match
    if text.count(old) == 1:
        edited = text.replace(old, new, 1)
        if filename.endswith(".py"):
            try:
                ast.parse(edited)
                return edited
            except (IndentationError, SyntaxError):
                pass  # Fall through to flexible indentation matching
        else:
            return edited

    # 2. Strip accidental line number prefixes from read_file (e.g. '21: ')
    import re
    stripped_old = re.sub(r"(?m)^\s*\d+:\s?", "", old)
    stripped_new = re.sub(r"(?m)^\s*\d+:\s?", "", new)
    if stripped_old and text.count(stripped_old) == 1:
        edited = text.replace(stripped_old, stripped_new, 1)
        if filename.endswith(".py"):
            try:
                ast.parse(edited)
                return edited
            except (IndentationError, SyntaxError):
                pass  # Fall through to flexible indentation matching
        else:
            return edited

    # 3. Flexible indentation matching: match relative indentation when base indentation differs
    cand_old = stripped_old if stripped_old else old
    cand_new = stripped_new if stripped_new else new
    text_lines = text.splitlines(keepends=True)
    old_lines = cand_old.splitlines()
    if old_lines:
        def get_base(lines):
            indents = [len(l) - len(l.lstrip(" ")) for l in lines if l.strip()]
            return min(indents) if indents else 0

        old_base = get_base(old_lines)
        old_rel = [l[old_base:].rstrip() for l in old_lines]
        k = len(old_lines)
        matches = []
        for i in range(len(text_lines) - k + 1):
            cand_slice = [l.rstrip() for l in text_lines[i : i + k]]
            cand_base = get_base(cand_slice)
            cand_rel = [l[cand_base:] if l.strip() else "" for l in cand_slice]
            if cand_rel == old_rel:
                matches.append((i, cand_base))

        if len(matches) == 1:
            idx, base = matches[0]
            new_lines = cand_new.splitlines()
            new_base = get_base(new_lines)
            indent_str = " " * base
            adjusted_new = [(indent_str + l[new_base:] if l.strip() else l) + "\n" for l in new_lines]
            edited = "".join(text_lines[:idx] + adjusted_new + text_lines[idx + k :])
            if filename.endswith(".py"):
                ast.parse(edited)
            return edited

    occurrences = text.count(old)
    raise ValueError(
        f"edit_file old text must match exactly once (found {occurrences}). "
        "Read the file section with read_file and provide unique surrounding context."
    )


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
    if tool == "edit_file":
        target = path(args["path"])
        edited = replace_unique(
            target.read_text(encoding="utf-8"), args["old"], args["new"], args["path"]
        )
        target.write_text(edited, encoding="utf-8")
        return "One exact replacement applied"
    if tool == "sql":
        import sqlite3

        db = sqlite3.connect(path(args["database"]))
        try:
            try:
                db.enable_load_extension(False)
            except (AttributeError, sqlite3.OperationalError):
                pass

            def authorize(action, *_):
                return (
                    sqlite3.SQLITE_DENY
                    if action in {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH}
                    else sqlite3.SQLITE_OK
                )

            db.set_authorizer(authorize)
            with db:
                cursor = db.execute(args["query"], args["parameters"])
                try:
                    return (
                        json.dumps(cursor.fetchmany(1000))
                        if cursor.description
                        else f"Rows changed: {cursor.rowcount}"
                    )
                finally:
                    cursor.close()
        finally:
            db.close()
    if tool in {"python", "run_tests"}:
        if tool == "python":
            argv = [sys.executable, "-c", args["code"]]
        else:
            raw_argv = args.get("argv")
            if not raw_argv:
                argv = [sys.executable, "-m", "pytest", "tests/", "-q"]
            elif isinstance(raw_argv, list):
                argv = list(raw_argv)
                # Remap python / pytest invocations to use active sys.executable
                if argv and argv[0] in {"python", "python3"}:
                    argv[0] = sys.executable
                elif argv and argv[0] == "pytest":
                    argv = [sys.executable, "-m", "pytest"] + argv[1:]
                # If model specified placeholder 'tests/test_file.py' and it doesn't exist, fallback to 'tests/'
                for i, arg in enumerate(argv):
                    if "test_file.py" in arg and not Path(arg).exists() and Path("tests").is_dir():
                        argv[i] = "tests/"
            else:
                argv = [sys.executable, "-m", "pytest", "tests/", "-q"]
        # Child stdout stays in the workspace/container; host reads at most max_output bytes.
        child_log = Path(tempfile.gettempdir()) / "veritas-child.log"
        with open(child_log, "wb") as log:
            result = subprocess.run(
                argv,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=int(os.environ.get("VERITAS_TIMEOUT", "55")),
                check=False,
            )
        with open(child_log, "rb") as log:
            text = log.read(16000).decode(errors="replace")
        return {"exit_code": result.returncode, "output": text}

    raise ValueError("Unsupported worker action")


if __name__ == "__main__":
    try:
        value = execute(json.loads(sys.stdin.read()))
        print(json.dumps(value if isinstance(value, dict) else {"exit_code": 0, "output": value}))
    except Exception as e:
        print(json.dumps({"exit_code": 1, "output": f"{type(e).__name__}: {e}"}))
