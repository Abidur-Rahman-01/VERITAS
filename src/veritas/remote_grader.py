"""
VERITAS Client for Remote Cloud Docker Evaluation.

Connects to a remote VERITAS Cloud Worker daemon (running on an external Linux machine)
or interacts with a remote Docker daemon via SSH / DOCKER_HOST to evaluate candidate patches
inside official SWE-rebench-V2 container images.
"""

import json
import logging
import os
import time
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

logger = logging.getLogger("veritas.remote_grader")


class RemoteDockerGrader:
    """Client for dispatching benchmark evaluations to a remote cloud worker."""

    def __init__(self, endpoint_url: Optional[str] = None, auth_token: Optional[str] = None):
        # Default to environment variable VERITAS_REMOTE_WORKER_URL or localhost
        self.endpoint = (endpoint_url or os.environ.get("VERITAS_REMOTE_WORKER_URL", "http://127.0.0.1:8080")).rstrip("/")
        self.auth_token = auth_token or os.environ.get("VERITAS_REMOTE_WORKER_TOKEN")

    def check_health(self) -> Dict[str, Any]:
        """Check whether the remote worker daemon and its Docker engine are reachable."""
        url = f"{self.endpoint}/health"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data
        except urllib.error.URLError as exc:
            return {"status": "unreachable", "error": str(exc), "endpoint": self.endpoint}

    def evaluate(
        self,
        image_name: str,
        patch: str,
        test_cmd: str,
        fail_to_pass: list[str],
        pass_to_pass: list[str],
        test_patch: Optional[str] = None,
        timeout: int = 240,
    ) -> Dict[str, Any]:
        """
        Send a candidate patch to the remote cloud worker for containerized execution.
        """
        url = f"{self.endpoint}/evaluate"
        payload = {
            "image_name": image_name,
            "patch": patch,
            "test_patch": test_patch,
            "test_cmd": test_cmd,
            "FAIL_TO_PASS": fail_to_pass,
            "PASS_TO_PASS": pass_to_pass,
            "timeout": timeout,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={**self._headers(), "Content-Type": "application/json"},
            method="POST",
        )

        start = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout + 30) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            logger.error(f"Remote evaluation HTTP error {exc.code}: {err_body}")
            return {
                "success": False,
                "resolved": False,
                "exit_code": exc.code,
                "error": f"HTTP {exc.code}: {err_body}",
                "duration_seconds": time.time() - start,
            }
        except Exception as exc:
            logger.error(f"Remote evaluation connection error: {exc}")
            return {
                "success": False,
                "resolved": False,
                "exit_code": 1,
                "error": str(exc),
                "duration_seconds": time.time() - start,
            }

    def _headers(self) -> Dict[str, str]:
        headers = {"User-Agent": "VERITAS-RemoteGrader/1.0"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers
