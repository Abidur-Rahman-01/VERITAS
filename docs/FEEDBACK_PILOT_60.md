# Historical 60-task pilot

The archived `feedback-calibration-qwen3-30b-60` run is an engineering pilot, not a canonical
SWE-rebench benchmark result. Its 60 task records had no `image_name` or `docker_image`, so the
then-current runner resolved local task setup functions and graded with local `pytest tests/`.
It also used a reference budget that was not enforced and pooled development and confirmation
outcomes descriptively.

Do not resume this study with the current runner. The current plan schema and protocol are
intentionally incompatible with that artifact. For a new image-backed staged run, follow
[FEEDBACK_CONFIRMATORY_RUN.md](FEEDBACK_CONFIRMATORY_RUN.md). Local fixtures remain available only
when both planning and execution explicitly pass `--allow-local-fixtures`; such results must be
reported as fixture pilots.
