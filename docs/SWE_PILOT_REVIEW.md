# Review of supplied SWE pilot transcript

This review checks the supplied command transcript and current source. The underlying
Windows runs/events.sqlite files, patches and official grading reports are not present
in this workspace. Reported token/time counts therefore cannot be independently
recomputed here. No model inference or benchmark evaluation was run during this review.

## Assessment

There is plausible infrastructure progress, but the reported table is not valid
evidence of calibrated verification performance or safety. Preserve all runs as
exploratory debugging artifacts.

## Findings

1. Calibration statistics for read_op and code_edit were manually inserted. In the
   actual fitting implementation, detection is an integer true-positive count divided
   by the number of errors. A detection rate of 0.75 cannot come from three error
   examples; 0.05 false-positive rate cannot come from seven correct examples. These
   entries are not measured statistics under the implemented estimator.

2. The tuning artifact's calibration hash was manually changed. Matching file hashes
   after editing does not mean thresholds were tuned with that artifact. Re-estimate
   the statistics from independent calibration records, then rerun tuning on validation.
   Do not bypass the identity check.

3. The policy runner counts error_label values but does not check label_scope or
   report missing labels. Unlabeled SWE actions contribute zero to both error and
   false-rejection counts. These aggregate metrics must remain unavailable until
   independently adjudicated, or explicitly be limited to a labeled subset.

4. The table reports patch presence/length, not official issue resolution. An empty
   patch is no solution, not evidence of safe behavior. A small patch is not inherently
   correct; a large patch is not inherently bloated. A verifier explanation cannot
   independently prove the rejected edit was defective.

5. As reported, RC-VoV used 47,321 tokens: 66.2% more than never (28,472) and 30.2%
   more than always (36,355), with eight verification calls and no patch. This does
   not demonstrate a cost or task-performance advantage. Without labels it could
   reflect false rejection, poor proposals, or other failures.

6. scripts/run_swe_online_comparison.py deletes incomplete run folders, excludes
   failed subprocess runs from the result list, and reuses existing runs without
   validating current config/artifact identity. It uses outer process runtime for new
   runs and an inner task-loop timer for reused runs. Its timings are not consistently
   defined. The task_id variable is printed but not used as an exact task selector.

7. The modified models.py silently replaces malformed critic probabilities with 0.5.
   The runtime identities omit the hard-coded prompt/parser version. Changes to these
   prompts invalidate old score/verifier calibration even if YAML stays unchanged.

8. The current swe.py resource stub can shadow the real Unix module. Global
   sitecustomize patches are not a validated portable harness implementation. Prefer a
   clean Linux/WSL2 evaluation environment, removing the unconditional stub from the
   project first, and explicitly version any required compatibility fixes.

## What can be retained

Keep original task selections, raw ledgers, original patches, model outputs, config
snapshots, image identities, grader stdout and failure logs. The repeatedly inspected
Astropy task remains a development/debugging case. The log's Gemini capacity error
alone does not establish that the local Qwen run failed; use its own failure.json and
summary records to determine that.

## Ordered recovery plan

1. Stop interpreting these tables as scientific evidence. Preserve the edited
   calibration/tuning files and all runs with a note explaining their invalid provenance.
2. Repair the runner so failures and unknown labels remain visible, no run directory
   is deleted, reuse checks a complete manifest, and runtime boundaries are consistent.
3. Validate the evaluation setup on this development task: run the official reference
   patch as an isolated evaluator control, and run an empty/unchanged baseline. Keep
   reference patches inaccessible to the policy/critic/verifier. Use unique grading
   run IDs, particularly after changing a patch or harness configuration.
4. Inspect actual per-instance report.json, test_output.txt and run_instance.log.
   Distinguish resolved, unresolved, empty patch and infrastructure error for every policy.
5. Fix critic parsing and include prompt/parser/weights/probe versions in model identities.
   Collect real SWE calibration actions and independent labels for missing action classes.
6. Fit a new immutable calibration artifact. Tune thresholds on disjoint validation
   tasks with that exact artifact. Reusing GSM-only thresholds on SWE is acceptable only
   as a declared frozen transfer test, not as validated SWE-specific optimization.
7. Freeze the system. Run 3–5 additional development tasks to confirm environment
   execution, then a predeclared pilot of 20–30 tasks across repositories. Use the same
   task list across policies and retain failed tasks. Choose final sample size from
   the pilot uncertainty and effect size, not from a promised improvement percentage.
8. Report task success, label coverage, false rejections, caught/missed errors, total
   policy/critic/verifier cost, time, actual spend, and budget compliance. Use independent
   task clusters for uncertainty; a single repeatedly attempted task is still one task.

Do not hand-fill empirical rates, refresh hashes to bypass checks, turn unknown labels
into zero errors, call blocked actions proven safety, or use patch length as task success.

Sources:
- https://www.swebench.com/SWE-bench/guides/evaluation/
- https://docs.python.org/3/library/resource.html
