import json
import time
import requests

verifier_models = [
    "deepseek-coder-v2:16b",
    "qwen2.5-coder:14b",
    "qwen2.5:14b",
    "deepseek-r1:14b",
]

prompt = (
    "You are a code verification gate.\n"
    "Evaluate the following proposed code change:\n"
    "File: cmd2/transcript.py\n"
    "Proposed change:\n"
    "- self.history.clear()\n"
    "Will this change cause a regression where transcript history is wiped when aborted?\n"
    "Respond strictly with either 'PASS' or 'FAIL: <reason>'."
)

for m in verifier_models:
    t0 = time.time()
    try:
        r = requests.post(
            "http://127.0.0.1:11434/api/chat",
            json={
                "model": m,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 100},
            },
            timeout=60,
        )
        dt = time.time() - t0
        content = r.json()["message"]["content"].strip().replace("\n", " ")
        print(f"Verifier {m:<22} ({dt:.2f}s): {content[:100]}")
    except Exception as e:
        print(f"Verifier {m:<22}: ERROR {e}")
