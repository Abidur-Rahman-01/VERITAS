"""GPU energy measurement by sampling ``nvidia-smi`` power draw (AgentStop-style reporting)."""

from __future__ import annotations

import shutil
import subprocess
import threading
import time


class EnergyMeter:
    """Context manager integrating board power over time. ``watt_hours`` is None without a GPU."""

    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self.watt_hours: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._joules = 0.0
        self._ok = shutil.which("nvidia-smi") is not None

    def _sample(self) -> float | None:
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5, check=True,
            ).stdout
            return sum(float(x) for x in out.split() if x.strip())
        except (subprocess.SubprocessError, ValueError, OSError):
            return None

    def _loop(self) -> None:
        last = time.monotonic()
        while not self._stop.is_set():
            watts = self._sample()
            now = time.monotonic()
            if watts is not None:
                self._joules += watts * (now - last)
            last = now
            self._stop.wait(self.interval)

    def __enter__(self) -> "EnergyMeter":
        if self._ok:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=10)
            self.watt_hours = self._joules / 3600.0
