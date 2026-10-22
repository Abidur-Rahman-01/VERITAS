import tempfile
import sys
from pathlib import Path
sys.path.insert(0, str(Path(".").resolve()))
from scripts.veritas_cloud_worker import run_cmd, to_container_mount_path

image_name = "swerebenchv2/altair-viz-altair:3068-d47f13b"
test_cmd = "pytest --no-header -rA --tb=line --color=no -p no:cacheprovider -W ignore::DeprecationWarning tests/test_examples.py"

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    run_script = tmp / "eval_runner.sh"
    script_content = [
        "#!/bin/bash",
        "set -e",
        "if [ -d /testbed/.git ]; then cd /testbed; elif [ -d /benchopt/.git ]; then cd /benchopt; elif git rev-parse --is-inside-work-tree >/dev/null 2>&1; then cd \"$(git rev-parse --show-toplevel)\"; fi",
        "echo \"Working in: $(pwd)\"",
        f"{test_cmd}",
    ]
    run_script.write_bytes(("\n".join(script_content) + "\n").encode("utf-8"))
    docker_args = [
        "docker", "run", "--rm",
        "-v", f"{to_container_mount_path(tmp)}:/veritas_mount:ro",
        image_name,
        "/bin/bash", "/veritas_mount/eval_runner.sh",
    ]
    code, stdout, stderr = run_cmd(docker_args, timeout=60)
    print("Code:", code)
    print("Stdout snippet:\n", stdout[-800:])
