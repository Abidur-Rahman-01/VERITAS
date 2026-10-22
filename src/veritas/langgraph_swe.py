"""Small LangGraph SWE-bench Lite agent with an explicit localization oracle ablation.

The oracle mode reveals only gold patch file paths. It never supplies the gold diff.
Those paths are benchmark labels, so oracle runs must not be reported as ordinary scores.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import TypedDict

import httpx
from langgraph.graph import END, START, StateGraph


class AgentState(TypedDict, total=False):
    task: dict
    repository: str
    oracle_paths: list[str]
    located_paths: list[str]
    diagnosis: str
    patch: str
    verification: dict
    repair_attempt: int


def model_call(base_url, model, system, prompt, api_key=None, timeout=300):
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    response = httpx.post(
        base_url.rstrip("/") + "/chat/completions",
        headers=headers,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def json_object(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object from model")
    return value


def source_snapshot(root, max_files=1200, max_bytes=180_000):
    ignored = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"}
    paths = []
    for path in sorted(root.rglob("*")):
        if any(part in ignored for part in path.parts) or not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith((".", "tests/")) and len(paths) > 80:
            continue
        paths.append(rel)
        if len(paths) >= max_files:
            break
    return paths


def file_context(root, paths, max_bytes=120_000):
    blocks, used = [], 0
    for rel in paths:
        path = (root / rel).resolve()
        if root.resolve() not in path.parents or not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        block = f"\n--- {rel} ---\n{body[:max_bytes]}"
        if used + len(block) > max_bytes:
            break
        blocks.append(block)
        used += len(block)
    return "".join(blocks)


def patch_paths(patch):
    found = []
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            found.append(line[6:].strip())
    return list(dict.fromkeys(found))


def clone_task(row, directory):
    repo_url = row["repo"]
    if "://" not in repo_url:
        repo_url = "https://github.com/" + repo_url
    subprocess.run(["git", "clone", "--quiet", "--filter=blob:none", repo_url, str(directory)], check=True)
    subprocess.run(["git", "-C", str(directory), "checkout", "--quiet", row["base_commit"]], check=True)


def build_graph(base_url, model, api_key=None, oracle_localization=False):
    def localize(state):
        root = Path(state["repository"])
        paths = source_snapshot(root)
        row = state["task"]
        if oracle_localization:
            return {"located_paths": state["oracle_paths"], "diagnosis": "Oracle file paths supplied from gold patch metadata."}
        result = json_object(model_call(
            base_url, model,
            "You are a fault localization specialist. Return JSON only: {\"files\":[relative paths],\"diagnosis\":\"brief evidence-based explanation\"}. Never claim certainty without evidence. Choose at most 8 files from the supplied repository file list.",
            json.dumps({"issue": row["problem_statement"], "repository_files": paths[:1500]}), api_key,
        ))
        selected = [p for p in result.get("files", []) if isinstance(p, str) and (root / p).is_file()]
        return {"located_paths": selected[:8], "diagnosis": str(result.get("diagnosis", ""))}

    def repair(state):
        root = Path(state["repository"])
        paths = state.get("located_paths", [])
        context = file_context(root, paths)
        result = json_object(model_call(
            base_url, model,
            "You are a repository repair specialist. Return JSON only with keys patch and rationale. patch must be a unified diff starting with diff --git, suitable for git apply. Use only the issue and source context. Do not emit the gold patch or unrelated edits.",
            json.dumps({"issue": state["task"]["problem_statement"], "files": paths,
                        "localization_diagnosis": state.get("diagnosis", ""),
                        "source_context": context, "previous_verification": state.get("verification")}),
            api_key,
        ))
        return {"patch": str(result.get("patch", "")), "repair_attempt": state.get("repair_attempt", 0) + 1}

    def verify(state):
        root = Path(state["repository"])
        patch = state.get("patch", "")
        check = subprocess.run(["git", "apply", "--check", "-"], cwd=root, input=patch,
                               text=True, capture_output=True)
        result = {"patch_applicable": check.returncode == 0, "message": (check.stderr or check.stdout)[-3000:]}
        if check.returncode == 0:
            applied = subprocess.run(["git", "apply", "-"], cwd=root, input=patch,
                                     text=True, capture_output=True)
            result["applied"] = applied.returncode == 0
            if applied.returncode == 0:
                whitespace = subprocess.run(["git", "diff", "--check"], cwd=root,
                                            text=True, capture_output=True)
                result["diff_check"] = whitespace.returncode == 0
                result["message"] = whitespace.stderr[-3000:]
        result["pass"] = bool(result.get("patch_applicable") and result.get("applied") and result.get("diff_check"))
        return {"verification": result}

    def after_verification(state):
        if not state.get("verification", {}).get("pass") and state.get("repair_attempt", 0) < 2:
            return "repair"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("localize", localize)
    graph.add_node("repair", repair)
    graph.add_node("verify", verify)
    graph.add_edge(START, "localize")
    graph.add_edge("localize", "repair")
    graph.add_edge("repair", "verify")
    graph.add_conditional_edges("verify", after_verification)
    return graph.compile()


def download_lite(output, revision="6ec7bb8"):
    from datasets import load_dataset

    rows = load_dataset("princeton-nlp/SWE-bench_Lite", split="test", revision=revision)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    manifest = {"dataset": "princeton-nlp/SWE-bench_Lite", "revision": revision,
                "split": "test", "rows": len(rows), "sha256": checksum}
    output.with_suffix(output.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**manifest, "path": str(output)}, indent=2))


def run(args):
    rows = [json.loads(line) for line in Path(args.tasks).read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        rows = rows[:args.limit]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    graph = build_graph(args.base_url, args.model, api_key, args.oracle_localization)
    results = []
    for row in rows:
        instance = row["instance_id"]
        workdir = output / "repos" / instance
        workdir.parent.mkdir(parents=True, exist_ok=True)
        clone_task(row, workdir)
        gold = patch_paths(row.get("patch", "")) if args.oracle_localization else []
        state = graph.invoke({"task": row, "repository": str(workdir), "oracle_paths": gold,
                              "repair_attempt": 0})
        result = {"instance_id": instance, "model_patch": state.get("patch", ""),
                  "model_name_or_path": args.model, "located_paths": state.get("located_paths", []),
                  "verification": state.get("verification", {}),
                  "localization_mode": "oracle_gold_patch_paths" if args.oracle_localization else "model",
                  "oracle_localization": bool(args.oracle_localization)}
        results.append(result)
        (output / f"{instance}.patch").write_text(result["model_patch"], encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k != "model_patch"}, ensure_ascii=False))
    with (output / "predictions.jsonl").open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps({k: result[k] for k in ("instance_id", "model_patch", "model_name_or_path")}, ensure_ascii=False) + "\n")
    with (output / "agent_results.jsonl").open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="LangGraph SWE-bench Lite agent")
    sub = parser.add_subparsers(dest="command", required=True)
    download = sub.add_parser("download", help="Download the 300-task SWE-bench Lite test split")
    download.add_argument("--output", default="data/swebench_lite.jsonl")
    download.add_argument("--revision", default="6ec7bb8")
    execute = sub.add_parser("run", help="Run localization -> repair -> verifier graph")
    execute.add_argument("--tasks", default="data/swebench_lite.jsonl")
    execute.add_argument("--output", default="runs/langgraph-swe-lite")
    execute.add_argument("--model", default="codestral:22b")
    execute.add_argument("--base-url", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434") + "/v1")
    execute.add_argument("--api-key-env", default="")
    execute.add_argument("--limit", type=int)
    execute.add_argument("--oracle-localization", action="store_true",
                         help="Leak gold patch file paths for an explicitly labeled oracle ablation")
    args = parser.parse_args()
    if args.command == "download":
        download_lite(args.output, args.revision)
    else:
        run(args)


if __name__ == "__main__":
    main()
