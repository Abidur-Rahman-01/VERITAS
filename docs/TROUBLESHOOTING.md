# Troubleshooting

| Symptom | Action |
|---|---|
| Docker daemon unavailable | Start Docker Desktop/service, rerun `veritas doctor`, then the integration test |
| Image not found | Build `Dockerfile.sandbox` for math, or build/pull the task's SWE image |
| No environment recipe for SWE training repository | Use supported `swe_test` research-pool tasks, the SWE-rebench fork, or provide that repository's image map |
| SWE-rebench install_config unsupported | Use `.venv-rebench/bin/veritas` after `scripts/setup_rebench.sh`, not the official harness environment |
| Model not found / HTTP 404 | Match `name` to the served model and check the correct base URL and backend |
| Missing/malformed model JSON | Inspect prompts, use an instruction-tuned model, increase completion tokens if truncated |
| Context overflow | Reduce history length; check the server's context limit; use a model supporting the task's input length |
| Probability fitting has only one label class | Collect more natural labeled traces; do not invent errors to make fitting run |
| Class lacks verifier/recovery statistics | Independently label correct and erroneous actions in `verifier_stats`; retain audit restoration trials |
| Replay rejects missing labels | Adjudicate all eligible actions under one scope; a verdict is not a label |
| Replay rejects missing verifier outcomes | Recollect ungated `audit_all` traces; selective online verification does not give complete counterfactual coverage |
| Critic/verifier identity mismatch | Reuse the fitted configuration, or rescore/recollect and refit calibration/tuning for the changed model |
| Data/hash mismatch | Keep the original artifact unchanged and create a new version/output directory |
| Existing run/export refuses overwrite | Use a new run/artifact directory to preserve experimental evidence |
| Container archive contains symlinks/special files | Current transaction backend rejects these tasks; record exclusion or implement and test a safe expanded backend |
| Workspace exceeds export limit | Inspect repository size; deliberately adjust limits and rerun container tests before adopting the new protocol |
| SWE task_success is null | Grade predictions with the official harness and supply its summary to `online-report` |
| Fewer source-specific tasks than raw release count | Cross-release duplicates were removed; inspect prepared assignments and source precedence |
| MATH answer marked wrong despite equivalence | Exact-string metric is intentionally limited; use independent symbolic/expert grading for publication |
| Token usage incomplete | The local endpoint omitted usage or a model request failed; do not interpret missing tokens as measured zero |

Set `VERITAS_DEBUG=1` to retain Python tracebacks. Run directories retain `failure.json`
and their append-only event ledger after failures. Scripts do not resume halfway through
an interrupted trajectory because the model context and exact process state would need
to be restored; rerun affected tasks under a new run ID.
