from pathlib import Path

p = Path("scripts/veritas_cloud_worker.py")
text = p.read_text(encoding="utf-8")

old = """        # Create evaluation bash script to execute inside the container
        run_script = tmp / "eval_runner.sh"
        script_content = [
            "#!/bin/bash",
            "set -e",
            "cd /benchopt 2>/dev/null || cd /testbed 2>/dev/null || cd /workspace 2>/dev/null || true",
            "# Reset working tree",
            "git reset --hard HEAD 2>/dev/null || true",
        ]

        if test_patch:
            script_content.append("git apply /veritas_mount/test.patch 2>/dev/null || true")

        # Apply candidate patch
        script_content.append("if [ -s /veritas_mount/changes.patch ]; then")
        script_content.append("  git apply --verbose /veritas_mount/changes.patch || patch -p1 < /veritas_mount/changes.patch")
        script_content.append("fi")"""

new = """        # Create evaluation bash script to execute inside the container
        run_script = tmp / "eval_runner.sh"
        script_content = [
            "#!/bin/bash",
            "set -e",
            "# Locate repository root",
            "if [ -d /testbed/.git ]; then cd /testbed; elif [ -d /benchopt/.git ]; then cd /benchopt; elif git rev-parse --is-inside-work-tree >/dev/null 2>&1; then cd \\\"$(git rev-parse --show-toplevel)\\\"; fi",
            "# Reset working tree",
            "git reset --hard HEAD 2>/dev/null || true",
        ]

        if test_patch:
            script_content.append("git apply /veritas_mount/test.patch 2>/dev/null || patch -p1 < /veritas_mount/test.patch 2>/dev/null || true")

        # Apply candidate patch
        script_content.append("if [ -s /veritas_mount/changes.patch ]; then")
        script_content.append("  git apply -v /veritas_mount/changes.patch 2>/dev/null || patch -p1 < /veritas_mount/changes.patch 2>/dev/null || true")
        script_content.append("fi")"""

assert old in text, "old block not found in scripts/veritas_cloud_worker.py"
p.write_text(text.replace(old, new), encoding="utf-8")
print("Updated scripts/veritas_cloud_worker.py with fixed repository working directory")
