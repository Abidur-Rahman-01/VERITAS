# Benchmark coverage and honest limits

The proposal mixes a core runtime with a catalogue of possible experiments. This
repository implements concrete, executable data/agent paths for the following entries.
No placeholder runner returns fabricated benchmark scores.

| Benchmark | Included support | Remaining requirement |
|---|---|---|
| SWE-bench / Verified | Original task download, task splits, official image names/builds, Docker agent, patches, official grader invocation | Working Docker; repository images; local models; actual test execution |
| SWE-rebench | Full original release, normalization, pinned upstream fork setup, image-map/build integration | Upstream fork environment/image build; historical dependencies can fail |
| GSM8K | Full original main train/test data, tool agent, independent numeric final-answer grading | Local model and Docker; intermediate-step adjudication |
| MATH-500 | Original release, tool agent, exact normalized final-answer metric | Symbolic equivalence/expert review if strict match is insufficient |

These listed proposal benchmarks are **not implemented as native runners**:

| Benchmark group | Why no claimed integrated result |
|---|---|
| HumanEvalFix, GSM-Symbolic | Corrupted-code/parametric task variants conflict with the requested no-synthetic-data default; not downloaded |
| GAIA / GAIA-Text-103 | Requires access-controlled data/attachments and a precisely defined subset; no invented 103-task substitute |
| XBench-DeepSearch | Needs live search/browsing tools and source-dependent grading; network tool execution is disabled here |
| AgentBoard, ScienceWorld, ALFWorld, BabyAI, PDDL | Different stateful environment APIs and simulator state recovery; filesystem rollback alone does not implement them |
| AgentDojo / ASB | Purpose-built simulated environments and attack corpora; not passed off as original real-world production interaction logs |
| EICU-AC / Mind2Web-SC | Exact releases, credentials/permissions and policy-specific evaluators are not supplied; no private clinical data is fabricated |
| CyberSecEval | Requires its own evaluation harness and risk definitions; AST checks are not a replacement |
| MultiArith, AQUA-RAT, StrategyQA | Dataset/task-specific loading and grading not included in this first implemented path |
| NEA CHF / bridge maintenance | No exact public dataset/version/modeling protocol identified in the supplied text |
| DiscoveryBench / POPPER | Need scientific data tables, statistical-test interfaces and independent hypothesis evaluators |

To extend to another environment, implement a sandbox with `workspace` and
`execute(ActionContract)`, an independent task evaluator, and its original task adapter.
Non-filesystem environments need their own transaction/snapshot interface rather than
pretending a directory snapshot covers simulator or external service state. Keep
private labels outside policy/verifier context and retain the same step/event schema.

`external_api` is a reserved taxonomy value with an impact weight, but no external tool
is enabled. SQLite operations are local sandbox database actions. They are not claims
of general production-database or email/API transaction support.

Storage is append-only SQLite plus Parquet/JSONL, not PostgreSQL. Recovery uses copied
workspace snapshots, not OverlayFS. The semantic verifier and optional pytest probes
are implemented; a separate general property-invariant language is not. Temperature
scaling is implemented; isotonic regression is not needed for the chosen calibration path.
These are explicit implementation choices, not unimplemented functions disguised as success.
