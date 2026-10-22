#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TASKS="${TASKS:-data/swebench_lite.jsonl}"
MODEL="${MODEL:-codestral:22b}"
VERIFIER_MODEL="${VERIFIER_MODEL:-llama3.1:8b}"
OLLAMA_HOST="${OLLAMA_HOST:-http://host.docker.internal:11434}"
OLLAMA_CHECK_URL="${OLLAMA_CHECK_URL:-http://127.0.0.1:11434}"
IMAGE_WORKERS="${IMAGE_WORKERS:-2}"
EVAL_WORKERS="${EVAL_WORKERS:-2}"
NAMESPACE="${NAMESPACE:-swebench}"
RUN_STAMP="${RUN_STAMP:-$(date +%Y%m%d-%H%M%S)}"
NORMAL_OUT="${NORMAL_OUT:-runs/langgraph-swe-lite-${RUN_STAMP}}"
ORACLE_OUT="${ORACLE_OUT:-runs/langgraph-swe-lite-oracle-${RUN_STAMP}}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI is required." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is unavailable. Start Docker Desktop/Engine and retry." >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1 || ! curl -fsS --max-time 5 \
  "${OLLAMA_CHECK_URL%/}/api/tags" >/dev/null; then
  echo "Ollama is unavailable at ${OLLAMA_CHECK_URL}. Start Ollama or set OLLAMA_CHECK_URL." >&2
  exit 1
fi
if ! curl -fsS --max-time 5 "${OLLAMA_CHECK_URL%/}/api/tags" \
  | python3 -c '
import json, sys
available = {item.get("name") for item in json.load(sys.stdin).get("models", [])}
required = sys.argv[1:]
missing = [name for name in required if name not in available]
if missing:
    print("Missing Ollama model(s): " + ", ".join(missing), file=sys.stderr)
    print("Pull them with: ollama pull <model>", file=sys.stderr)
    raise SystemExit(1)
' "$MODEL" "$VERIFIER_MODEL"; then
  echo "Pull the required models before running the full experiment." >&2
  exit 1
fi
if [[ ! -f "$TASKS" ]]; then
  echo "Task dataset not found at $TASKS; downloading the pinned SWE-bench Lite split." >&2
fi
if [[ -e "$NORMAL_OUT" || -e "$ORACLE_OUT" ]]; then
  echo "Run output path already exists. Set NORMAL_OUT and ORACLE_OUT to new paths." >&2
  exit 1
fi

export OLLAMA_HOST

echo "[1/7] Building the agent image"
docker compose build swe-langgraph

if [[ ! -f "$TASKS" ]]; then
  echo "[2/7] Downloading task dataset"
  docker compose run --rm --entrypoint python swe-langgraph \
    -m veritas.langgraph_swe download --output "$TASKS"
else
  echo "[2/7] Reusing $TASKS"
fi

echo "[3/7] Building SWE-bench task images (can take hours and substantial disk space)"
docker compose run --rm --entrypoint veritas veritas swe build-images \
  "$TASKS" --workers "$IMAGE_WORKERS"

echo "[4/7] Running standard model localization arm"
docker compose run --rm swe-langgraph run \
  --tasks "$TASKS" --model "$MODEL" --verifier-model "$VERIFIER_MODEL" \
  --output "$NORMAL_OUT"

echo "[5/7] Running Oracle localization arm"
docker compose run --rm swe-langgraph run \
  --tasks "$TASKS" --model "$MODEL" --verifier-model "$VERIFIER_MODEL" \
  --oracle-localization --output "$ORACLE_OUT"

echo "[6/7] Evaluating standard arm"
docker compose run --rm --entrypoint python swe-langgraph \
  -m swebench.harness.run_evaluation \
  --dataset_name "$TASKS" --predictions_path "$NORMAL_OUT/predictions.jsonl" \
  --max_workers "$EVAL_WORKERS" --run_id "langgraph-lite-${RUN_STAMP}" \
  --namespace "$NAMESPACE"

echo "[7/7] Evaluating Oracle localization arm"
docker compose run --rm --entrypoint python swe-langgraph \
  -m swebench.harness.run_evaluation \
  --dataset_name "$TASKS" --predictions_path "$ORACLE_OUT/predictions.jsonl" \
  --max_workers "$EVAL_WORKERS" --run_id "langgraph-lite-oracle-${RUN_STAMP}" \
  --namespace "$NAMESPACE"

echo "Experiment complete. Agent outputs: $NORMAL_OUT and $ORACLE_OUT"
