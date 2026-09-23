import ast
from pathlib import PurePosixPath

from pydantic import Field, StrictStr

from .schema import ActionClass, ActionContract, Proposal, StrictModel


class PathArgs(StrictModel):
    path: StrictStr


class ListArgs(StrictModel):
    path: StrictStr = "."
    limit: int = Field(default=200, ge=1, le=1000, strict=True)


class ReadArgs(PathArgs):
    start_line: int = Field(default=1, ge=1, strict=True)
    max_lines: int = Field(default=200, ge=1, le=1000, strict=True)


class WriteArgs(PathArgs):
    content: StrictStr = Field(max_length=1_000_000)


class PythonArgs(StrictModel):
    code: StrictStr = Field(max_length=100_000)


class TestArgs(StrictModel):
    argv: list[StrictStr] = Field(min_length=1, max_length=100)


class SQLArgs(StrictModel):
    database: StrictStr
    query: StrictStr = Field(max_length=100_000)
    parameters: list = Field(default_factory=list)


class FinalArgs(StrictModel):
    answer: StrictStr = Field(max_length=100_000)


ARG_TYPES = {
    "list_files": ListArgs,
    "read_file": ReadArgs,
    "write_file": WriteArgs,
    "delete_file": PathArgs,
    "python": PythonArgs,
    "run_tests": TestArgs,
    "sql": SQLArgs,
    "final_answer": FinalArgs,
}


def valid_path(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or "\x00" in value:
        raise ValueError("Paths must be relative and remain inside the workspace")
    if any(part in {".git", ".ssh", ".env", ".veritas"} for part in path.parts):
        raise ValueError("Protected path")
    return value


def contract(proposal: Proposal):
    args = ARG_TYPES[proposal.tool].model_validate(proposal.args).model_dump()
    for key in ("path", "database"):
        if key in args:
            valid_path(args[key])
    tool = proposal.tool
    if tool == "python":
        ast.parse(args["code"])
    if tool == "write_file" and args["path"].endswith(".py"):
        ast.parse(args["content"])
    if tool == "run_tests":
        argv = args["argv"]
        allowed = argv[0] == "pytest" or argv[:3] in (
            ["python", "-m", "pytest"],
            ["python3", "-m", "pytest"],
        )
        if not allowed:
            raise ValueError("run_tests permits pytest only; use python for sandboxed code")
        if any("\x00" in part for part in argv):
            raise ValueError("NUL in argument")
    # SQL never executes on a host database. Even SELECT may invoke functions:
    # classify every SQL operation conservatively as a reversible DB mutation.
    if tool in {"list_files", "read_file"}:
        cls, mutation, perms = ActionClass.READ, "none", ["workspace:read"]
    elif tool == "write_file":
        cls, mutation, perms = ActionClass.EDIT, "local", ["workspace:write"]
    elif tool == "sql":
        cls, mutation, perms = ActionClass.DB, "database", ["workspace:database"]
    elif tool == "final_answer":
        cls, mutation, perms = ActionClass.FINAL, "none", ["answer:submit"]
    else:
        cls, mutation, perms = ActionClass.ENV, "environment", ["sandbox:execute"]
    return ActionContract(
        proposal=Proposal(tool=tool, args=args),
        action_class=cls,
        permissions=perms,
        mutation_type=mutation,
        reversible=tool != "final_answer",
    )
