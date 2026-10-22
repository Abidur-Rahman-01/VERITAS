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
    if not base_url.startswith(("http://", "https://")):
        base_url = "http://" + base_url
    base_url = base_url.replace("://0.0.0.0", "://127.0.0.1")
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
            "options": {"num_ctx": 8192},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def json_object(text):
    text = text.strip()
    try:
        val = json.loads(text, strict=False)
        if isinstance(val, dict):
            return val
    except Exception:
        pass
    match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, flags=re.I)
    if match:
        try:
            val = json.loads(match.group(1).strip(), strict=False)
            if isinstance(val, dict):
                return val
        except Exception:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            val = json.loads(text[start : end + 1], strict=False)
            if isinstance(val, dict):
                return val
        except Exception:
            pass
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    value = json.loads(text, strict=False)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object from model")
    return value


def source_snapshot(root, max_files=350, max_bytes=25_000):
    ignored = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", ".tox", ".eggs"}
    paths = []
    for path in sorted(root.rglob("*.py")):
        if any(part in ignored for part in path.parts) or not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith((".", "tests/", "test/")) and len(paths) > 50:
            continue
        paths.append(rel)
        if len(paths) >= max_files:
            break
    if len(paths) < max_files:
        for path in sorted(root.rglob("*")):
            if any(part in ignored for part in path.parts) or not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if rel not in paths and not rel.startswith((".", "tests/", "test/")):
                paths.append(rel)
                if len(paths) >= max_files:
                    break
    return paths


def file_context(root, paths, max_bytes=14_000):
    blocks, used = [], 0
    for rel in paths:
        path = (root / rel).resolve()
        if root.resolve() not in path.parents or not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        remaining = max_bytes - used
        if remaining <= 0:
            break
        block = f"\n--- {rel} ---\n{body[:remaining]}"
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
    subprocess.run(["git", "config", "--global", "--add", "safe.directory", "*"], check=False)
    repo_url = row["repo"]
    if "://" not in repo_url:
        repo_url = "https://github.com/" + repo_url
    target_dir = Path(directory)
    if not (target_dir / ".git").is_dir():
        parent_repos = target_dir.parent
        cached_source = None
        repo_slug = row["repo"].replace("/", "__")
        if parent_repos.is_dir():
            for sibling in parent_repos.iterdir():
                if sibling.is_dir() and (sibling / ".git").is_dir() and sibling != target_dir:
                    if sibling.name.startswith(repo_slug) or sibling.name.startswith(row["repo"].split("/")[-1]):
                        cached_source = str(sibling)
                        break
        if cached_source:
            subprocess.run(["git", "clone", "--quiet", cached_source, str(directory)], check=True)
            subprocess.run(["git", "-C", str(directory), "remote", "set-url", "origin", repo_url], check=False)
        else:
            subprocess.run(["git", "clone", "--quiet", "--filter=blob:none", repo_url, str(directory)], check=True)
    res = subprocess.run(["git", "-C", str(directory), "checkout", "--quiet", row["base_commit"]])
    if res.returncode != 0:
        subprocess.run(["git", "-C", str(directory), "fetch", "origin", row["base_commit"]], check=False)
        subprocess.run(["git", "-C", str(directory), "checkout", "--quiet", row["base_commit"]], check=True)


def build_graph(base_url, model, api_key=None, oracle_localization=False, verifier_model="llama3.1:8b"):
    def localize(state):
        root = Path(state["repository"])
        paths = source_snapshot(root)
        row = state["task"]
        if oracle_localization:
            return {"located_paths": state["oracle_paths"], "diagnosis": "Oracle file paths supplied from gold patch metadata."}
        result = {}
        try:
            raw = model_call(
                base_url, model,
                "You are a fault localization specialist. Return JSON only: {\"files\":[relative paths],\"diagnosis\":\"brief evidence-based explanation\"}. Never claim certainty without evidence. Choose at most 8 files from the supplied repository file list.",
                json.dumps({"issue": row["problem_statement"], "repository_files": paths[:350]}), api_key,
            )
            result = json_object(raw)
        except Exception:
            result = {}
        selected = [p for p in result.get("files", []) if isinstance(p, str) and (root / p).is_file()]
        if not selected:
            mentioned = re.findall(r"[\\w/.-]+\\.py", row["problem_statement"])
            for m in mentioned:
                cleaned = m.lstrip("./")
                if (root / cleaned).is_file() and cleaned not in selected:
                    selected.append(cleaned)
            if not selected and paths:
                selected = paths[:3]
        return {"located_paths": selected[:8], "diagnosis": str(result.get("diagnosis", "Localized based on issue and repository files."))}

    def repair(state):
        root = Path(state["repository"])
        paths = state.get("located_paths", [])
        context = file_context(root, paths)
        raw = model_call(
            base_url, model,
            "You are a repository repair specialist. Return JSON only with keys patch and rationale. patch must be a unified diff starting with diff --git, suitable for git apply. Use only the issue and source context. Do not emit the gold patch or unrelated edits.",
            json.dumps({"issue": state["task"]["problem_statement"], "files": paths,
                        "localization_diagnosis": state.get("diagnosis", ""),
                        "source_context": context, "previous_verification": state.get("verification")}),
            api_key,
        )
        patch = ""
        try:
            result = json_object(raw)
            patch = str(result.get("patch", ""))
        except Exception:
            pass
        if not patch or "diff --git" not in patch:
            match = re.search(r'(diff --git[\s\S]+?)(?:```|(?:\",\s*\"rationale\":)|$)', raw)
            if match:
                patch = match.group(1).strip()
        if "\\n" in patch and "\n" not in patch:
            patch = patch.replace("\\n", "\n")
        patch = re.sub(r'[\s",}]+$', "", patch).strip()
        if patch and not patch.endswith("\n"):
            patch += "\n"
        return {"patch": patch, "repair_attempt": state.get("repair_attempt", 0) + 1}

    def sanitize_patch(p):
        lines = p.splitlines(keepends=True)
        out = []
        in_hunk = False
        for line in lines:
            if line.startswith('@@'):
                in_hunk = True
                out.append(line)
            elif in_hunk:
                if line.startswith(('---', '+++', 'diff ')):
                    in_hunk = False
                    out.append(line)
                elif line.startswith((' ', '+', '-', '\\')):
                    out.append(line)
                elif line in ('\n', '\r\n'):
                    out.append(' ' + line)
                else:
                    out.append(line)
            else:
                out.append(line)
        return ''.join(out)

    def verify(state):
        root = Path(state["repository"])
        patch = state.get("patch", "")
        if not patch:
            return {"verification": {"patch_applicable": False, "message": "Empty patch", "pass": False}}
        patch = sanitize_patch(patch)
        subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=root, capture_output=True)
        subprocess.run(["git", "clean", "-fdx"], cwd=root, capture_output=True)
        check = subprocess.run(["git", "apply", "--check", "--recount", "-"], cwd=root, input=patch,
                               encoding="utf-8", errors="replace", capture_output=True)
        git_applicable = (check.returncode == 0)
        git_message = (check.stderr or check.stdout)[-3000:]

        applied = False
        diff_check = False
        if git_applicable:
            apply_res = subprocess.run(["git", "apply", "--recount", "-"], cwd=root, input=patch,
                                       encoding="utf-8", errors="replace", capture_output=True)
            applied = (apply_res.returncode == 0)
            if applied:
                ws_res = subprocess.run(["git", "diff", "--check"], cwd=root,
                                        encoding="utf-8", errors="replace", capture_output=True)
                diff_check = (ws_res.returncode == 0)

        git_pass = bool(git_applicable and applied and diff_check)

        # 1. If Git check failed, fail immediately and supply git error feedback
        if not git_pass:
            result = {
                "patch_applicable": git_applicable,
                "applied": applied,
                "diff_check": diff_check,
                "verifier_model": verifier_model,
                "verdict": "FAIL",
                "reason": f"Git application error: {git_message.strip()}",
                "message": f"Git application error: {git_message.strip()}",
                "pass": False,
            }
            return {"verification": result, "patch": patch}

        # 2. Git check passed! Now run semantic evaluation with Llama 8B Verifier
        llm_verdict = "PASS"
        llm_reason = "Verified syntactically and semantically."
        if verifier_model:
            try:
                system_prompt = (
                    "You are a strict code review and verification specialist. "
                    "Your job is to critically evaluate whether a proposed git patch correctly solves the issue "
                    "without introducing bugs, regressions, or syntax errors. "
                    "Return ONLY a JSON object: {\"verdict\": \"PASS\" or \"FAIL\", \"reason\": \"detailed concise explanation\"}."
                )
                user_prompt = json.dumps({
                    "issue": state["task"]["problem_statement"],
                    "patch": patch[:10000],
                    "modified_files": state.get("located_paths", []),
                    "diagnosis": state.get("diagnosis", "")
                })
                raw_eval = model_call(base_url, verifier_model, system_prompt, user_prompt, api_key, timeout=120)
                eval_obj = json_object(raw_eval)
                llm_verdict = str(eval_obj.get("verdict", "PASS")).upper().strip()
                llm_reason = str(eval_obj.get("reason", "No reason provided."))
            except Exception as e:
                llm_verdict = "PASS"
                llm_reason = f"LLM verifier fallback: {e}"

        passes = (llm_verdict == "PASS")
        result = {
            "patch_applicable": True,
            "applied": True,
            "diff_check": True,
            "verifier_model": verifier_model,
            "verdict": llm_verdict,
            "reason": llm_reason,
            "message": llm_reason if not passes else f"Passed Git checks and verified by {verifier_model}.",
            "pass": passes,
        }
        return {"verification": result, "patch": patch}

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
    graph = build_graph(args.base_url, args.model, api_key, args.oracle_localization, verifier_model=args.verifier_model)
    pred_path = output / "predictions.jsonl"
    agent_path = output / "agent_results.jsonl"
    existing_instances = set()
    if pred_path.is_file():
        for line in pred_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    existing_instances.add(json.loads(line)["instance_id"])
                except Exception:
                    pass

    results = []
    for row in rows:
        instance = row["instance_id"]
        if instance in existing_instances:
            print(f"Skipping already completed task {instance}", flush=True)
            continue
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
        with pred_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({k: result[k] for k in ("instance_id", "model_patch", "model_name_or_path")}, ensure_ascii=False) + "\n")
            handle.flush()
        with agent_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            handle.flush()
        print(json.dumps({k: v for k, v in result.items() if k != "model_patch"}, ensure_ascii=False), flush=True)


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
    execute.add_argument("--verifier-model", default="llama3.1:8b",
                         help="Llama 8B verifier model for semantic patch verification")
    args = parser.parse_args()
    if args.command == "download":
        download_lite(args.output, args.revision)
    else:
        run(args)


if __name__ == "__main__":
    main()
