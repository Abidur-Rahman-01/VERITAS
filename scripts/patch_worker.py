import os
import sys
from pathlib import Path

target_file = Path("scripts/veritas_cloud_worker.py")
code = target_file.read_text(encoding="utf-8")

# Replace write_text with write_bytes for script and patches
code = code.replace(
    'patch_file.write_text(patch, encoding="utf-8")',
    'patch_file.write_bytes(patch.encode("utf-8"))'
)
code = code.replace(
    'test_patch_file.write_text(test_patch, encoding="utf-8")',
    'test_patch_file.write_bytes(test_patch.encode("utf-8"))'
)
code = code.replace(
    'run_script.write_text("\\n".join(script_content) + "\\n", encoding="utf-8")',
    'run_script.write_bytes(("\\n".join(script_content) + "\\n").replace("\\r\\n", "\\n").encode("utf-8"))'
)

target_file.write_text(code, encoding="utf-8")
print("Successfully updated veritas_cloud_worker.py for unix line endings!")
