#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
records=${1:?Usage: bash scripts/run_offline.sh annotated-records.jsonl output-directory}
output=${2:?Output directory required}
mkdir -p "$output"
.venv/bin/veritas calibrate "$records" --output "$output/calibration.json"
.venv/bin/veritas tune "$records" --artifact "$output/calibration.json" \
  --output "$output/tuning.json" --budgets 0.02 0.04 0.1 0.2 0.4
.venv/bin/veritas replay "$records" --artifact "$output/calibration.json" \
  --tuning "$output/tuning.json" --output "$output/replay" --budgets 0.02 0.04 0.1 0.2 0.4
.venv/bin/veritas report "$output/replay"
