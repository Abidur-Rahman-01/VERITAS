# VERITAS v2

VERITAS is a research codebase for studying coding agents and verification.

The proposed paper asks whether a coding agent changes its repair behavior when told its work
may be reviewed, even when no verifier feedback is delivered. It separates that **evaluation
awareness** effect from the effect of assigned verifier feedback using a randomized four-condition
design. The main protocol discloses a 50% review-selection probability in the disclosure arms,
with balanced review assignment in both disclosure conditions. The v2 implementation includes
frozen planning, draft/revision execution, bounded patch review, independent SWE grading,
factorial analysis, pilot power simulation, and static gate calibration/transfer.
The implementation and its new tests have **not been executed or validated in this change**.
No model runs or research results are claimed.

Read [the architecture and research guide](docs/ARCHITECTURE.md) for the full research question,
block diagrams, literature map, dataset and model recommendations, code/function map, runtime
status, implementation locations, and experiment plan. It is the only detailed Markdown project
guide in `docs/`.

## CLI workflows

From the repository root:

```sh
uv sync --frozen --extra dev --extra swe
uv run veritas --help
```

`veritas awareness` provides `split`, `plan`, `verify`, `run`, `resume`, `grade`, `audit`,
`report`, `check-cue`, `power`, `fit-gate`, `calibrate-gate`, and `gate-report`.
Start from [the example protocol](configs/awareness-pilot.example.yaml). Planning reads the
prepared dataset and installed grader package; it does not call models or Docker. Execution,
grading, and cue checks are separate commands. The architecture documents their required order.

Existing commands such as `veritas collect` and `veritas compare` retain their separate workflows.

The [implementation architecture](docs/ARCHITECTURE.md#8-implementation-architecture) specifies
one Python coordinator, isolated Docker workspaces, a draft → review/control → revision workflow,
and independent SWE grading. Each arm gets the same actor allowance; one patch review bounds
verifier cost. It includes module interfaces, persistence and recovery rules, resource estimates,
and the staged research pipeline. Actor attempts are never automatically retried; resume retains
interrupted attempts and grading retries use a frozen patch with a fresh grading identity.

The v2 review corrects the code reuse assumptions, distinguishes assigned review from delivered
feedback, separates deferred audit costs, and requires a graded power pilot. The
[Stage 0–6 pipeline](docs/ARCHITECTURE.md#17-end-to-end-pipeline-and-implementation-order) ends
with a held-out calibration-transfer test; it does not assume awareness violates a gate's target.
