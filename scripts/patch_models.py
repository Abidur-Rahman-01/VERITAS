from pathlib import Path

p = Path("src/veritas/models.py")
text = p.read_text(encoding="utf-8")

old = '''        elif cfg.backend == "ollama":
            payload = {"model": cfg.name, "messages": messages, "stream": False,
                       "format": "json", "options": {"temperature": cfg.temperature,
                                                       "num_predict": cap}}'''

new = '''        elif cfg.backend == "ollama":
            payload = {"model": cfg.name, "messages": messages, "stream": False,
                       "format": "json", "options": {"temperature": cfg.temperature,
                                                       "num_predict": cap,
                                                       "num_ctx": 8192}}'''

assert old in text, "Target block not found"
p.write_text(text.replace(old, new), encoding="utf-8")
print("Updated src/veritas/models.py with num_ctx: 8192")
