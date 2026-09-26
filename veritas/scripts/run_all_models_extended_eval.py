"""Extended Task Evaluation across 8 Open-Source Models (1B to 14B Parameters).

Models evaluated on RTX 5080:
1. Llama 3.2 1B (llama3.2:1b)
2. Qwen 2.5 1.5B (qwen2.5:1.5b)
3. Gemma 2 2B (gemma2:2b)
4. Llama 3.2 3B (llama3.2:3b)
5. Qwen 2.5-Coder 7B (qwen2.5-coder:7b)
6. Mistral 7B (mistral:7b)
7. Llama 3.1 8B (llama3.1:8b)
8. Qwen 2.5-Coder 14B (qwen2.5-coder:14b)

Metrics captured:
- Mathematical & Multi-Step Reasoning Accuracy (%)
- Action Contract Structuring Latency (ms) & Validity
- Calibrated Error Probability Prior p_error
- Inference Latency per Step (ms)
- VRAM Usage & Memory Efficiency
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from veritas.actions.contracts import ActionContract
from veritas.eval.gsm8k import load_gsm8k_dataset
from veritas.models.base import PolicyContext
from veritas.models.ollama_client import OllamaClient, OllamaErrorEstimator, OllamaPolicy


MODELS_SPECTRUM = [
    {"name": "llama3.2:1b", "scale": "1B", "family": "Llama 3.2", "vram_gb": 1.3},
    {"name": "qwen2.5:1.5b", "scale": "1.5B", "family": "Qwen 2.5", "vram_gb": 1.0},
    {"name": "gemma2:2b", "scale": "2B", "family": "Gemma 2", "vram_gb": 1.6},
    {"name": "llama3.2:3b", "scale": "3B", "family": "Llama 3.2", "vram_gb": 2.0},
    {"name": "qwen2.5-coder:7b", "scale": "7B", "family": "Qwen 2.5 Coder", "vram_gb": 4.7},
    {"name": "mistral:7b", "scale": "7B", "family": "Mistral", "vram_gb": 4.1},
    {"name": "llama3.1:8b", "scale": "8B", "family": "Llama 3.1", "vram_gb": 4.7},
    {"name": "qwen2.5-coder:14b", "scale": "14B", "family": "Qwen 2.5 Coder", "vram_gb": 9.0},
]


def evaluate_single_model(model_info: dict, problems: list, test_contract_ctx: PolicyContext) -> dict:
    model_name = model_info["name"]
    scale = model_info["scale"]
    family = model_info["family"]
    vram = model_info["vram_gb"]

    client = OllamaClient(model_name=model_name, timeout_seconds=90.0)
    if not client.is_available():
        return {"model": model_name, "status": "offline"}

    installed = client.list_models()
    matching = [m for m in installed if model_name in m]
    if not matching:
        return {"model": model_name, "status": "not_installed"}

    full_name = matching[0]
    client.model_name = full_name
    policy = OllamaPolicy(client)
    estimator = OllamaErrorEstimator(client)

    print(f"\n=======================================================")
    print(f"--> BENCHMARKING: {family} ({scale}) -> {full_name}")
    print(f"=======================================================")

    # 1. Multi-Step Reasoning on Extended Problems
    correct = 0
    gen_latencies = []
    for prob in problems:
        prompt = (
            f"Solve this math problem step by step.\n"
            f"Question: {prob.question}\n"
            f"End your response with '#### <number>' on the final line."
        )
        t0 = time.perf_counter()
        resp = client.generate(prompt, temperature=0.0)
        t1 = time.perf_counter()
        gen_latencies.append((t1 - t0) * 1000.0)

        target_str = str(int(prob.final_answer)) if prob.final_answer.is_integer() else str(prob.final_answer)
        if f"#### {target_str}" in resp or f"####  {target_str}" in resp:
            correct += 1

    avg_latency_ms = sum(gen_latencies) / max(1, len(gen_latencies))
    accuracy_pct = (correct / max(1, len(problems))) * 100.0

    # 2. Action Contract Structuring
    t0 = time.perf_counter()
    action = policy.propose_action(test_contract_ctx)
    t1 = time.perf_counter()
    structuring_latency_ms = (t1 - t0) * 1000.0
    valid_contract = action is not None and bool(action.tool) and bool(action.operation)

    # 3. Error Risk Estimation
    if action:
        t0 = time.perf_counter()
        est = estimator.estimate(test_contract_ctx, action)
        t1 = time.perf_counter()
        est_score = est.raw_score
        est_latency_ms = (t1 - t0) * 1000.0
    else:
        est_score = 0.20
        est_latency_ms = 0.0

    return {
        "model": model_name,
        "family": family,
        "scale": scale,
        "vram_gb": vram,
        "problems_tested": len(problems),
        "reasoning_accuracy_percent": round(accuracy_pct, 1),
        "avg_step_latency_ms": round(avg_latency_ms, 1),
        "contract_structuring_latency_ms": round(structuring_latency_ms, 1),
        "valid_contract": valid_contract,
        "tool_proposed": action.tool if action else "none",
        "operation_proposed": action.operation if action else "none",
        "calibrated_risk_prior": round(est_score, 3),
        "status": "success",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate 1B to 14B models on extended tasks")
    parser.add_argument("--problems", type=int, default=10, help="Number of extended math reasoning tasks")
    parser.add_argument("--output-json", type=Path, default=Path("research/results/extended_models_eval.json"))
    parser.add_argument("--output-csv", type=Path, default=Path("research/results/extended_models_eval.csv"))
    args = parser.parse_args()

    problems = load_gsm8k_dataset(limit=args.problems)
    print(f"Loaded {len(problems)} extended multi-step reasoning problems.")

    test_ctx = PolicyContext(
        goal="Audit Django ORM queryset cache invalidation and quarantine stale model instances",
        step_index=0,
        history=(),
    )

    all_results = []
    for m in MODELS_SPECTRUM:
        res = evaluate_single_model(m, problems, test_ctx)
        all_results.append(res)
        if res.get("status") == "success":
            print(f"[{m['scale']}] {m['name']:18s} | Acc: {res['reasoning_accuracy_percent']:5.1f}% | Latency: {res['avg_step_latency_ms']:6.1f} ms | Contract: {res['valid_contract']} | Prior: {res['calibrated_risk_prior']}")
        else:
            print(f"[{m['scale']}] {m['name']:18s} | Status: {res.get('status')}")

    # Save JSON
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n--> Saved extended evaluation JSON to {args.output_json}")

    # Save CSV for successful runs
    success_rows = [r for r in all_results if r.get("status") == "success"]
    if success_rows:
        keys = list(success_rows[0].keys())
        with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(success_rows)
        print(f"--> Saved extended evaluation CSV to {args.output_csv}")


if __name__ == "__main__":
    main()
