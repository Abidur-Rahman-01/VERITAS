from pathlib import Path
import re

p1 = Path("scripts/veritas_cloud_worker.py")
text1 = p1.read_text(encoding="utf-8")
target1 = """def run_cmd(argv, timeout=300, input_data: Optional[bytes] = None) -> tuple[int, str, str]:
    \"\"\"Execute command with timeout and return (exit_code, stdout, stderr).\"\"\"
    env = os.environ.copy()
    if sys.platform == "win32" and "DOCKER_HOST" not in env:
        env["DOCKER_HOST"] = "tcp://172.23.21.138:2375"
    try:"""
repl1 = """def get_docker_host() -> str:
    if "DOCKER_HOST" in os.environ:
        return os.environ["DOCKER_HOST"]
    if sys.platform == "win32":
        ip = "172.23.21.138"
        try:
            r = subprocess.run(["wsl", "-d", "Ubuntu", "hostname", "-I"], capture_output=True, text=True, timeout=3)
            if r.returncode == 0 and r.stdout.strip():
                ip = r.stdout.strip().split()[0]
        except Exception:
            pass
        host = f"tcp://{ip}:2375"
        os.environ["DOCKER_HOST"] = host
        return host
    return ""


def run_cmd(argv, timeout=300, input_data: Optional[bytes] = None) -> tuple[int, str, str]:
    \"\"\"Execute command with timeout and return (exit_code, stdout, stderr).\"\"\"
    env = os.environ.copy()
    if sys.platform == "win32":
        env["DOCKER_HOST"] = get_docker_host()
    try:"""
assert target1 in text1, "target1 not found in scripts/veritas_cloud_worker.py"
p1.write_text(text1.replace(target1, repl1), encoding="utf-8")
print("Updated scripts/veritas_cloud_worker.py")
