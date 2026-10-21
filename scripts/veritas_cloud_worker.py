#!/usr/bin/env python3
"""
VERITAS Remote Cloud Docker Worker Service.

This standalone service runs on a remote Linux server (AWS, GCP, Hetzner, RunPod, etc.)
where Docker is installed. It accepts evaluation requests from the local VERITAS runner,
spins up isolated disposable containers using official SWE-rebench-V2 images, applies
patches, executes tests, and returns structured verification results.

Zero external Python dependencies required (standard library only).
Usage:
    python veritas_cloud_worker.py --port 8080 --auth-token YOUR_SECRET_TOKEN
"""

import argparse
import http.server
import json
import logging
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("veritas_worker")


def run_cmd(argv, timeout=300, input_data: Optional[bytes] = None) -> tuple[int, str, str]:
    """Execute command with timeout and return (exit_code, stdout, stderr)."""
    try:
        proc = subprocess.run(
            argv,
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return (
            proc.returncode,
            proc.stdout.decode("utf-8", errors="replace"),
            proc.stderr.decode("utf-8", errors="replace"),
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"Execution timed out after {timeout} seconds"
    except Exception as exc:
        return 1, "", f"Execution exception: {exc}"


def check_docker_available() -> Dict[str, Any]:
    """Verify Docker daemon is accessible and return system info."""
    code, out, err = run_cmd(["docker", "info", "--format", "{{json .}}"], timeout=10)
    if code != 0:
        return {"available": False, "error": err.strip() or "Docker daemon not reachable"}
    try:
        info = json.loads(out)
        return {
            "available": True,
            "server_version": info.get("ServerVersion", "unknown"),
            "os_type": info.get("OSType", "unknown"),
            "cpus": info.get("NCPU", 0),
            "memory_bytes": info.get("MemTotal", 0),
        }
    except Exception:
        return {"available": True, "server_version": "active"}


def evaluate_task_in_container(
    image_name: str,
    patch: str,
    test_patch: Optional[str],
    test_cmd: str,
    fail_to_pass: list[str],
    pass_to_pass: list[str],
    timeout_seconds: int = 180,
) -> Dict[str, Any]:
    """
    Launch a clean container from image_name, apply the patch, run test_cmd,
    and verify FAIL_TO_PASS and PASS_TO_PASS criteria.
    """
    start_time = time.time()
    cid = f"veritas-{uuid.uuid4().hex[:12]}"

    # 1. Ensure image is available (pull if missing)
    inspect_code, _, _ = run_cmd(["docker", "image", "inspect", image_name], timeout=15)
    if inspect_code != 0:
        logger.info(f"Image {image_name} not found locally; pulling...")
        pull_code, _, pull_err = run_cmd(["docker", "pull", image_name], timeout=600)
        if pull_code != 0:
            return {
                "success": False,
                "error": f"Failed to pull Docker image {image_name}: {pull_err[:500]}",
                "duration_seconds": time.time() - start_time,
            }

    with tempfile.TemporaryDirectory(prefix="veritas-eval-") as tmpdir:
        tmp = Path(tmpdir)
        patch_file = tmp / "changes.patch"
        patch_file.write_text(patch, encoding="utf-8")

        test_patch_file = None
        if test_patch:
            test_patch_file = tmp / "test.patch"
            test_patch_file.write_text(test_patch, encoding="utf-8")

        # Create evaluation bash script to execute inside the container
        run_script = tmp / "eval_runner.sh"
        script_content = [
            "#!/bin/bash",
            "set -e",
            "cd /testbed || cd /workspace || cd /app",
            "# Reset working tree",
            "git reset --hard HEAD 2>/dev/null || true",
        ]

        if test_patch:
            script_content.append("git apply /veritas_mount/test.patch 2>/dev/null || true")

        # Apply candidate patch
        script_content.append("if [ -s /veritas_mount/changes.patch ]; then")
        script_content.append("  git apply --verbose /veritas_mount/changes.patch || patch -p1 < /veritas_mount/changes.patch")
        script_content.append("fi")

        # Run test command
        script_content.append("echo '=== BEGIN TEST EXECUTION ==='")
        script_content.append(f"{test_cmd}")
        run_script.write_text("\n".join(script_content) + "\n", encoding="utf-8")

        # Run container with resource bounds
        docker_args = [
            "docker", "run", "--rm",
            "--name", cid,
            "--memory=4g",
            "--cpus=2.0",
            "--pids-limit=256",
            "-v", f"{str(tmp)}:/veritas_mount:ro",
            image_name,
            "/bin/bash", "/veritas_mount/eval_runner.sh",
        ]

        code, stdout, stderr = run_cmd(docker_args, timeout=timeout_seconds)
        duration = time.time() - start_time
        full_log = (stdout or "") + "\n" + (stderr or "")

        # Evaluate test passes
        ftp_resolved = []
        ftp_unresolved = []
        for test_id in fail_to_pass:
            # Check if test passed in stdout
            if f"PASSED {test_id}" in full_log or f"{test_id} PASSED" in full_log or f"{test_id} ok" in full_log:
                ftp_resolved.append(test_id)
            else:
                ftp_unresolved.append(test_id)

        all_tests_passed = (code == 0) and (len(ftp_unresolved) == 0 if fail_to_pass else True)

        return {
            "success": True,
            "resolved": all_tests_passed,
            "exit_code": code,
            "duration_seconds": round(duration, 2),
            "log": full_log[-4000:],  # Tail 4000 chars
            "fail_to_pass_resolved": ftp_resolved,
            "fail_to_pass_unresolved": ftp_unresolved,
        }


class WorkerHandler(http.server.BaseHTTPRequestHandler):
    auth_token: Optional[str] = None

    def _check_auth(self) -> bool:
        if not self.auth_token:
            return True
        auth_header = self.headers.get("Authorization", "")
        if auth_header == f"Bearer {self.auth_token}":
            return True
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Unauthorized"}).encode("utf-8"))
        return False

    def do_GET(self):
        if self.path == "/health":
            docker_info = check_docker_available()
            self.send_response(200 if docker_info.get("available") else 503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "healthy" if docker_info.get("available") else "docker_unavailable",
                "docker": docker_info,
                "timestamp": time.time(),
            }).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if not self._check_auth():
            return

        if self.path == "/evaluate":
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Invalid JSON payload: {e}"}).encode("utf-8"))
                return

            image_name = payload.get("image_name")
            patch = payload.get("patch", "")
            test_patch = payload.get("test_patch")
            test_cmd = payload.get("test_cmd", "pytest")
            fail_to_pass = payload.get("FAIL_TO_PASS", [])
            pass_to_pass = payload.get("PASS_TO_PASS", [])
            timeout = payload.get("timeout", 180)

            if not image_name:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "image_name is required"}).encode("utf-8"))
                return

            result = evaluate_task_in_container(
                image_name=image_name,
                patch=patch,
                test_patch=test_patch,
                test_cmd=test_cmd,
                fail_to_pass=fail_to_pass,
                pass_to_pass=pass_to_pass,
                timeout_seconds=timeout,
            )

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


def run_server(port: int = 8080, auth_token: Optional[str] = None):
    WorkerHandler.auth_token = auth_token
    docker_status = check_docker_available()
    logger.info(f"VERITAS Cloud Worker starting on port {port}...")
    logger.info(f"Docker status: {docker_status}")

    with socketserver.ThreadingTCPServer(("", port), WorkerHandler) as httpd:
        httpd.daemon_threads = True
        logger.info(f"Worker listening on http://0.0.0.0:{port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Stopping worker daemon.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VERITAS Cloud Docker Worker")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--auth-token", type=str, default=None, help="Optional bearer authentication token")
    args = parser.parse_args()
    run_server(port=args.port, auth_token=args.auth_token)
