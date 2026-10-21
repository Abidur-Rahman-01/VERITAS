# VERITAS v2

VERITAS is a research codebase for studying coding agents and verification.

VERITAS studies long-horizon LLM problem solving with iterative verification and autonomous repair.
The repository includes full benchmark runners for reasoning and code tasks, SWE repository
workflows, model comparisons, verifier/controller policies, and a separate evaluation-awareness
factorial study. The awareness study is a distinct research line, not the main paper framing.

The high-level paper opportunity is to measure when verifier-guided repair improves independently
graded task success, how often it repairs an initially failing answer, and what added compute it
costs. See [the architecture and research guide](docs/ARCHITECTURE.md) for the proposed controlled
comparisons and evidence requirements. Keep claims grounded in their source artifacts; passing
software tests alone does not validate research results.

Read [the architecture and research guide](docs/ARCHITECTURE.md) for the paper direction, system
map, study designs, evidence requirements, and implementation notes. It is the detailed Markdown
project guide in `docs/`.

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
