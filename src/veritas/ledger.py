"""Append-only, hash-chained event ledger.

Every decision, cost, grade and artifact hash is appended as one JSON line whose ``hash`` covers
the previous line's hash, so any later edit or deletion is detectable with :meth:`Ledger.verify`.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .util import append_jsonl, sha256_json, utc_now

GENESIS = "0" * 64


class LedgerCorrupt(RuntimeError):
    pass


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._last = GENESIS
        if self.path.exists():
            self._last = self.verify()

    def append(self, kind: str, **payload) -> dict:
        with self._lock:
            event = {"kind": kind, "time": utc_now(), "prev": self._last, **payload}
            event["hash"] = sha256_json({k: v for k, v in event.items() if k != "hash"})
            append_jsonl(self.path, event)
            self._last = event["hash"]
            return event

    def events(self, kind: str | None = None):
        if not self.path.exists():
            return
        with open(self.path, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    event = json.loads(line)
                    if kind is None or event["kind"] == kind:
                        yield event

    def verify(self) -> str:
        """Check the whole chain; return the last hash. Raises LedgerCorrupt on any mismatch."""
        previous = GENESIS
        for number, event in enumerate(self.events(), 1):
            if event.get("prev") != previous:
                raise LedgerCorrupt(f"{self.path}: broken chain at event {number}")
            expected = sha256_json({k: v for k, v in event.items() if k != "hash"})
            if event.get("hash") != expected:
                raise LedgerCorrupt(f"{self.path}: tampered event {number}")
            previous = event["hash"]
        return previous

    def completed(self, unit_kind: str) -> set[str]:
        """Keys of units recorded as finished; used to resume a phase without redoing work."""
        return {e["key"] for e in self.events("unit_done") if e.get("unit") == unit_kind}

    def mark_done(self, unit_kind: str, key: str, **payload) -> dict:
        return self.append("unit_done", unit=unit_kind, key=key, **payload)
