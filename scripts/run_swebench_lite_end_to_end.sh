#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TASKS="${TASKS:-data/swebench_lite.jsonl}"
MODEL="${MODEL:-qwen3-coder:30b}"
OPENHANDS_MODEL="${OPENHANDS_MODEL:-openai/${MODEL}}"
VERIFIER_MODEL="${VERIFIER_MODEL:-qwen2.5-coder:14b}"
LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:11434/v1}"
LLM_API_KEY="${LLM_API_KEY:-ollama}"
VERIFIER_BASE_URL="${VERIFIER_BASE_URL:-http://127.0.0.1:11434}"
LIMIT="${LIMIT:-3}"
OFFSET="${OFFSET:-0}"
MAX_VERIFIER_ROUNDS="${MAX_VERIFIER_ROUNDS:-3}"
EVAL_MODAL="${EVAL_MODAL:-true}"
RUN_STAMP="${RUN_STAMP:-$(date +%Y%m%d-%H%M%S)}"
NORMAL_OUT="${NORMAL_OUT:-runs/openhands-swe-lite-${RUN_STAMP}}"
DATASET_NAME="princeton-nlp/SWE-bench_Lite"

for required in uv openhands git curl; do
  if ! command -v "$required" >/dev/null 2>&1; then
    echo "Required command not found: $required" >&2
    exit 1
  fi
done

if [[ "$EVAL_MODAL" == "false" ]] && ! command -v docker >/dev/null 2>&1; then
  echo "Local SWE-bench grading needs Docker, but the docker command was not found." >&2
  exit 1
fi

if ! curl -fsS --max-time 5 "${LLM_BASE_URL%/}/models" >/dev/null; then
  echo "Cannot reach OpenHands' OpenAI-compatible Ollama endpoint at ${LLM_BASE_URL}." >&2
  echo "Start Ollama and set OLLAMA_CONTEXT_LENGTH=32768 before running OpenHands." >&2
  exit 1
fi

if ! curl -fsS --max-time 10 "${VERIFIER_BASE_URL%/}/api/tags" | \
  uv run python -c 'import json,sys; names={m.get("name") for m in json.load(sys.stdin).get("models", [])}; sys.exit(0 if set(sys.argv[1:]) <= names else 1)' \
  "$MODEL" "$VERIFIER_MODEL"; then
  echo "Ollama at $VERIFIER_BASE_URL must have both '$MODEL' and '$VERIFIER_MODEL' installed." >&2
  echo "Pull them on the Ollama host, then retry." >&2
  exit 1
fi

if [[ -e "$NORMAL_OUT" ]]; then
  echo "Run output path already exists. Choose a new NORMAL_OUT path." >&2
  exit 1
fi

export LLM_BASE_URL LLM_API_KEY

if [[ ! -f "$TASKS" ]]; then
  echo "Downloading the pinned SWE-bench Lite test split to $TASKS"
  uv run --extra swe python -m veritas.openhands_swe download --output "$TASKS"
fi

echo "Running OpenHands with actor $OPENHANDS_MODEL and verifier $VERIFIER_MODEL (offset: $OFFSET, limit: $LIMIT)"
uv run --extra swe python -m veritas.openhands_swe run \
  --tasks "$TASKS" --model "$OPENHANDS_MODEL" \
  --offset "$OFFSET" --limit "$LIMIT" --output "$NORMAL_OUT" \
  --verifier-model "$VERIFIER_MODEL" --verifier-base-url "$VERIFIER_BASE_URL" \
  --max-verifier-rounds "$MAX_VERIFIER_ROUNDS"

if [[ "$EVAL_MODAL" == "true" ]]; then
  echo "Evaluating predictions on Modal"
else
  echo "Evaluating predictions in local SWE-bench Docker containers"
fi
uv run --extra swe \
  python -m swebench.harness.run_evaluation \
  --dataset_name "$DATASET_NAME" \
  --predictions_path "$NORMAL_OUT/predictions.jsonl" \
  --max_workers 2 \
  --run_id "openhands-lite-${RUN_STAMP}" \
  --modal "$EVAL_MODAL"

echo "Done. Agent logs, predictions, and per-task resources: $NORMAL_OUT"
echo "Set LIMIT=300 for the full Lite test split after the pilot works."
