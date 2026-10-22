#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TASKS="${TASKS:-data/swebench_lite.jsonl}"
MODEL="${MODEL:-qwen3-coder:30b}"
OPENHANDS_MODEL="${OPENHANDS_MODEL:-openai/${MODEL}}"
LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:11434/v1}"
LLM_API_KEY="${LLM_API_KEY:-ollama}"
LIMIT="${LIMIT:-3}"
RUN_STAMP="${RUN_STAMP:-$(date +%Y%m%d-%H%M%S)}"
NORMAL_OUT="${NORMAL_OUT:-runs/openhands-swe-lite-${RUN_STAMP}}"
ORACLE_OUT="${ORACLE_OUT:-runs/openhands-swe-lite-oracle-${RUN_STAMP}}"
DATASET_NAME="princeton-nlp/SWE-bench_Lite"

for required in uv openhands ollama git curl; do
  if ! command -v "$required" >/dev/null 2>&1; then
    echo "Required command not found: $required" >&2
    exit 1
  fi
done

if ! curl -fsS --max-time 5 "${LLM_BASE_URL%/}/models" >/dev/null; then
  echo "Cannot reach the OpenAI-compatible Ollama endpoint at ${LLM_BASE_URL}." >&2
  echo "Start Ollama and set OLLAMA_CONTEXT_LENGTH=32768 before running OpenHands." >&2
  exit 1
fi

if ! ollama list | awk 'NR > 1 { print $1 }' | grep -Fxq "$MODEL"; then
  echo "Ollama model '$MODEL' is not installed. Run: ollama pull $MODEL" >&2
  exit 1
fi

if [[ -e "$NORMAL_OUT" || -e "$ORACLE_OUT" ]]; then
  echo "Run output path already exists. Choose new NORMAL_OUT and ORACLE_OUT paths." >&2
  exit 1
fi

export LLM_BASE_URL LLM_API_KEY

if [[ ! -f "$TASKS" ]]; then
  echo "Downloading the pinned SWE-bench Lite test split to $TASKS"
  uv run --extra swe python -m veritas.openhands_swe download --output "$TASKS"
fi

echo "Running the standard-navigation arm with model $OPENHANDS_MODEL (limit: $LIMIT)"
uv run --extra swe python -m veritas.openhands_swe run \
  --tasks "$TASKS" --model "$OPENHANDS_MODEL" \
  --limit "$LIMIT" --output "$NORMAL_OUT"

echo "Running the oracle-file-path arm"
uv run --extra swe python -m veritas.openhands_swe run \
  --tasks "$TASKS" --model "$OPENHANDS_MODEL" \
  --limit "$LIMIT" --oracle-localization --output "$ORACLE_OUT"

echo "Evaluating both arms on Modal (no local Docker daemon required)"
for arm in normal oracle; do
  if [[ "$arm" == "normal" ]]; then
    output="$NORMAL_OUT"
  else
    output="$ORACLE_OUT"
  fi
  uv run --extra swe \
    python -m swebench.harness.run_evaluation \
    --dataset_name "$DATASET_NAME" \
    --predictions_path "$output/predictions.jsonl" \
    --max_workers 2 \
    --run_id "openhands-lite-${arm}-${RUN_STAMP}" \
    --modal true
done

echo "Done. Agent logs and predictions: $NORMAL_OUT and $ORACLE_OUT"
echo "Set LIMIT=300 for the full Lite test split after the pilot works."
