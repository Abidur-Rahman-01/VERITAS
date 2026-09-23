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
                sandbox = DockerSandbox(clone, self.sandbox_config)
                outcome = sandbox.execute(action)
                if outcome["exit_code"] != 0:
                    return Verification(
                        verdict="FAIL",
                        reason="Candidate execution: " + outcome["output"],
                        cost=cost,
                    )
                for argv in self.probes:
                    result = sandbox.execute(
                        contract(Proposal(tool="run_tests", args={"argv": argv}))
                    )
                    if result["exit_code"] != 0:
                        return Verification(
                            verdict="FAIL",
                            reason="Configured probe: " + result["output"],
                            cost=cost,
                        )
        return self.model.verify(context, action, cost)
