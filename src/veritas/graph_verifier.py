"""Evidence-producing graph verifier. No model code executes on the host.

Only trusted local checks produce FAIL. A model's negative opinion produces REVIEW,
which the runtime may use for one bounded final-answer revision. PASS means no
checked defect was found, never a proof that the task is solved.
"""

import ast
import copy
import shutil
import tempfile
import time
from collections import OrderedDict
from pathlib import Path

from .contracts import contract
from .graph import DAG, Node
from .io import digest
from .sandbox import DockerSandbox
from .sanitize import redact
from .schema import Proposal, Usage, Verification


class GraphVerifier:
    def __init__(self, model, sandbox_config, probes, settings):
        self.model, self.sandbox_config = model, sandbox_config
        self.probes, self.settings = probes, settings
        self.cache = OrderedDict()
        self.semantic_calls = 0
        for argv in probes:
            contract(Proposal(tool="run_tests", args={"argv": argv}))

    def plan(self, action, review_available):
        tool = action.proposal.tool
        nodes, targets = [], []
        if tool in {"write_file", "edit_file", "delete_file"}:
            nodes += [Node("candidate"), Node("syntax", ("candidate",))]
            targets.append("syntax")
            for i, _ in enumerate(self.probes):
                # Independent baseline and candidate branches join at each differential probe.
                nodes += [
                    Node(f"baseline:{i}", (), 10),
                    Node(f"regression:{i}", ("syntax", f"baseline:{i}"), 20),
                ]
                if i < self.settings.max_probes:
                    targets.append(f"regression:{i}")
        if tool == "final_answer":
            nodes.append(Node("semantic", (), 100))
            if review_available:
                targets.append("semantic")
        nodes.append(Node("decision", tuple(targets), 1000))
        return DAG(nodes)

    def _candidate(self, action, workspace):
        tool, args = action.proposal.tool, action.proposal.args
        target = Path(workspace) / args["path"]
        # Runtime hashes reject symlinks too; keep this boundary safe for direct callers.
        root = Path(workspace).resolve()
        if target.is_symlink() or root not in target.resolve().parents:
            raise ValueError("Candidate path must remain inside the workspace")
        if tool in {"edit_file", "delete_file"} and not target.is_file():
            return {
                "status": "FAIL",
                "reason": "Read an existing file before editing/deleting it.",
                "certificate": {"check": "file_exists", "path": args["path"], "exists": False},
            }
        if tool == "delete_file":
            return {"status": "PASS", "text": None}
        if tool == "write_file":
            text = args["content"]
        else:
            if target.stat().st_size > self.settings.max_file_bytes:
                raise ValueError("File exceeds configured graph checker byte limit")
            text = target.read_text(encoding="utf-8")
            matches = text.count(args["old"])
            if matches != 1:
                return {
                    "status": "FAIL",
                    "reason": "Re-read the file; old must match exactly once.",
                    "certificate": {
                        "check": "unique_edit",
                        "path": args["path"],
                        "matches": matches,
                        "file_sha256": digest(text),
                        "old_sha256": digest(args["old"]),
                    },
                }
            text = text.replace(args["old"], args["new"], 1)
        if len(text.encode("utf-8")) > self.settings.max_file_bytes:
            raise ValueError("Candidate exceeds configured graph checker byte limit")
        return {"status": "PASS", "text": text}

    def _probe(self, workspace, argv, action=None):
        # A fresh clone per branch prevents tests from contaminating other graph nodes.
        with tempfile.TemporaryDirectory(prefix="veritas-graph-") as temp:
            clone = Path(temp) / "workspace"
            shutil.copytree(workspace, clone)
            sandbox = DockerSandbox(clone, self.sandbox_config)
            if action is not None:
                candidate = sandbox.execute(action)
                if candidate["exit_code"] != 0:
                    raise ValueError("Candidate probe setup failed: " + candidate["output"][:300])
            return sandbox.execute(contract(Proposal(tool="run_tests", args={"argv": argv})))

    def verify_graph(self, context, action, cost, workspace, state_hash, budget, allow_review=True):
        start = time.monotonic()
        available = (
            self.settings.semantic_final_review
            and allow_review
            and self.semantic_calls < self.settings.max_semantic_calls
            and budget.can_afford(cost)
        )
        graph = self.plan(action, available)
        trace = graph.describe(["decision"])
        trace.update(
            {
                "checks": [],
                "cache_hits": 0,
                "semantic_calls": 0,
                "state_hash": state_hash,
                "semantic_review_available": available,
            }
        )
        results, usage, spent = {}, Usage(), 0.0
        verdict, reason, certificate, basis = (
            "PASS",
            "No checked defect found",
            None,
            "deterministic",
        )
        for name in trace["schedule"]:
            if name == "decision":
                continue
            # Only pure deterministic checks are cached. Tests and model reviews can be stochastic.
            cacheable = name in {"candidate", "syntax"}
            key = digest([name, state_hash, action.model_dump(mode="json")])
            cached = cacheable and key in self.cache
            try:
                if cached:
                    result = copy.deepcopy(self.cache[key])
                    self.cache.move_to_end(key)
                    trace["cache_hits"] += 1
                elif name == "candidate":
                    result = self._candidate(action, workspace)
                elif name == "syntax":
                    text = results["candidate"].get("text")
                    result = {"status": "PASS"}
                    if text is not None and action.proposal.args["path"].endswith(".py"):
                        try:
                            ast.parse(text)
                        except SyntaxError as e:
                            result = {
                                "status": "FAIL",
                                "reason": f"Fix Python syntax at line {e.lineno}: {e.msg}",
                                "certificate": {
                                    "check": "python_ast",
                                    "line": e.lineno,
                                    "message": e.msg,
                                    "candidate_sha256": digest(text),
                                },
                            }
                elif name.startswith("baseline:"):
                    outcome = self._probe(workspace, self.probes[int(name.split(":")[1])])
                    result = {
                        "status": "PASS",
                        "exit_code": outcome["exit_code"],
                        "output_sha256": digest(outcome["output"]),
                    }
                    if outcome["exit_code"] not in {0, 1}:
                        result.update(
                            status="ERROR", reason="Baseline pytest did not complete normally"
                        )
                elif name.startswith("regression:"):
                    index = int(name.split(":")[1])
                    before = results[f"baseline:{index}"]
                    if before["exit_code"] != 0:
                        # A pre-existing failure cannot establish a new regression; save the candidate run.
                        result = {"status": "SKIP", "reason": "Baseline already fails"}
                    else:
                        after = self._probe(workspace, self.probes[index], action)
                        result = {"status": "PASS"}
                        if after["exit_code"] == 1:
                            certificate = {
                                "check": "configured_test_regression",
                                "argv": self.probes[index],
                                "before_exit": 0,
                                "after_exit": 1,
                                "state_hash": state_hash,
                                "action_sha256": digest(action.model_dump(mode="json")),
                                "before_output_sha256": before["output_sha256"],
                                "after_output_sha256": digest(after["output"]),
                            }
                            result = {
                                "status": "FAIL",
                                "reason": "Configured test passed before the edit and failed after it: "
                                + redact(after["output"])[-300:],
                                "certificate": certificate,
                            }
                        elif after["exit_code"] != 0:
                            result = {
                                "status": "ERROR",
                                "reason": "Candidate pytest did not complete normally",
                            }
                elif name == "semantic":
                    budget.charge(cost)  # Charge BEFORE inference, even on errors.
                    spent += cost
                    self.semantic_calls += 1
                    trace["semantic_calls"] += 1
                    review = self.model.verify(context, action, cost)
                    usage = review.usage
                    basis = "model_opinion"
                    status = "REVIEW" if review.verdict in {"FAIL", "REVIEW"} else review.verdict
                    result = {"status": status, "reason": review.reason, "basis": "model_opinion"}
                else:
                    raise ValueError(f"Unknown verifier node: {name}")
            except Exception as e:
                if name == "semantic":
                    usage = getattr(e, "usage", Usage(measured=False))
                result = {"status": "ERROR", "reason": redact(f"{type(e).__name__}: {e}")[:400]}
            results[name] = result
            if cacheable and not cached and result["status"] in {"PASS", "FAIL"}:
                self.cache[key] = copy.deepcopy(result)
                while len(self.cache) > self.settings.cache_entries:
                    self.cache.popitem(last=False)
            trace["checks"].append(
                {
                    "node": name,
                    "status": result["status"],
                    "cached": cached,
                    "certificate": result.get("certificate"),
                    "reason": redact(result.get("reason", ""))[:400],
                }
            )
            if result["status"] in {"FAIL", "ERROR", "REVIEW"}:
                verdict, reason = result["status"], result["reason"]
                certificate = result.get("certificate")
                basis = result.get("basis", "deterministic" if verdict == "FAIL" else "unspecified")
                break  # Stop dependent/expensive work after a failure or unavailable prerequisite.
        trace["seconds"] = time.monotonic() - start
        trace["skipped_nodes"] = [n for n in graph.nodes if n not in results and n != "decision"]
        return Verification(
            verdict=verdict,
            reason=redact(reason)[:400],
            usage=usage,
            cost=spent,
            basis=basis,
            certificate=certificate,
        ), trace
