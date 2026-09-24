import json
import shutil
import tempfile
from pathlib import Path

from .contracts import contract
from .sandbox import DockerSandbox
from .schema import Proposal, Verification


class Verifier:
    def __init__(self, model, sandbox_config, probes=None):
        self.model, self.sandbox_config, self.probes = model, sandbox_config, probes or []
        # Probe commands are supplied by experimenter configuration, never model output.
        for argv in self.probes:
            contract(Proposal(tool="run_tests", args={"argv": argv}))

    def verify(self, context, action, cost, workspace):
        if self.probes and action.mutation_type != "none":
            with tempfile.TemporaryDirectory(prefix="veritas-probe-") as temp:
                clone = Path(temp) / "workspace"
                shutil.copytree(workspace, clone)
                baseline = Path(temp) / "baseline"
                shutil.copytree(workspace, baseline)
                baseline_sandbox = DockerSandbox(baseline, self.sandbox_config)
                sandbox = DockerSandbox(clone, self.sandbox_config)
                outcome = sandbox.execute(action)
                if outcome["exit_code"] != 0:
                    return Verification(
                        verdict="FAIL",
                        reason="Candidate execution: " + outcome["output"],
                        cost=cost,
                    )
                evidence = []
                for argv in self.probes:
                    probe = contract(Proposal(tool="run_tests", args={"argv": argv}))
                    before = baseline_sandbox.execute(probe)
                    result = sandbox.execute(probe)
                    evidence.append({"argv": argv, "before": before, "candidate": result})
                    if before["exit_code"] == 0 and result["exit_code"] != 0:
                        return Verification(
                            verdict="FAIL",
                            reason="Configured probe newly fails after candidate: "
                            + result["output"],
                            cost=cost,
                        )
                # Existing failing tests are expected in bug-fix tasks. They are not proof
                # that an intermediate edit is wrong. Give both outcomes to the model.
                context = json.dumps({"context": context, "untrusted_probe_evidence": evidence})
        return self.model.verify(context, action, cost)
