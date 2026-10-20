import json
import time
import requests

models = [
    "qwen2.5-coder:14b",
    "deepseek-coder-v2:16b",
    "granite-code:20b",
    "starcoder2:15b",
    "deepcoder:14b",
]

prompt = (
    "You are an autonomous software engineering agent.\n"
    "To solve the task, use JSON tool calls in the format:\n"
    '```json\n{"name": "edit_file", "arguments": {"path": "cmd2/ansi.py", "old_str": "return f\'\\\\033[{color_code}m{text}\\\\033[0m\'", "new_str": "if os.environ.get(\'NO_COLOR\'): return text\\n    return f\'\\\\033[{color_code}m{text}\\\\033[0m\'"}}\n```\n'
    "Task: In `cmd2/ansi.py`, modify `colorize` so that if `NO_COLOR` is set in the environment, it returns `text` without ANSI formatting. Return the tool call JSON now."
)

print(f"{'Model':<25} | {'Latency':<8} | {'Valid Tool Call':<16} | {'Sample Output'}")
print("-" * 80)

for m in models:
    t0 = time.time()
    try:
        r = requests.post(
            "http://127.0.0.1:11434/api/chat",
            json={
                "model": m,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 200},
            },
            timeout=120,
        )
        dt = time.time() - t0
        content = r.json()["message"]["content"]
        has_tool = "```json" in content or '"name":' in content
        sample = content.strip().replace("\n", " ")[:60]
        print(f"{m:<25} | {dt:<8.2f}s | {str(has_tool):<16} | {sample}")
    except Exception as e:
        print(f"{m:<25} | ERROR: {e}")
