"""Single-coordinator study ledger with durable call reservations and hashed events."""

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import Field

from .io import canonical, digest, file_hash, write_json, write_text
from .sanitize import redact
from .schema import StrictModel, Usage


class StudyBudgetExceeded(RuntimeError):
    pass


ACTIVE_STATES = {"running", "draft_frozen", "boundary_recorded", "final_frozen"}
TERMINAL_STATES = {"completed", "failed", "interrupted", "budget_stopped"}
TRANSITIONS = {"running": {"draft_frozen"}, "draft_frozen": {"boundary_recorded"},
               "boundary_recorded": {"final_frozen"}, "final_frozen": set()}


class TrialOutcome(StrictModel):
    trial_id: str
    attempt_id: str = "attempt-001"
    runtime_status: Literal["completed", "failed", "interrupted", "budget_stopped"]
    error: str | None = None
    draft_patch_hash: str | None = None
    final_patch_hash: str | None = None
    draft_tree_hash: str | None = None
    final_tree_hash: str | None = None
    image_digest: str | None = None
    phase_results: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)
    seconds: float | None = Field(default=None, ge=0)
    failure_category: str | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)


@contextmanager
def coordinator_lock(root):
    with (Path(root) / "coordinator.lock").open("a+") as handle:
        try:
            import fcntl
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("Another coordinator is using this study") from exc
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
        except ImportError:
            import msvcrt
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("Another coordinator is using this study") from exc
            try:
                yield
            finally:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass


class StudyStore:
    def __init__(self, root):
        self.root = Path(root)
        self.db = sqlite3.connect(self.root / "study.sqlite")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS trials(
                trial_id TEXT PRIMARY KEY, ordinal INTEGER NOT NULL, assignment TEXT NOT NULL,
                status TEXT NOT NULL, outcome TEXT);
            CREATE TABLE IF NOT EXISTS events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL,
                previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS immutable_event_update BEFORE UPDATE ON events
                BEGIN SELECT RAISE(ABORT, 'append-only study events'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_event_delete BEFORE DELETE ON events
                BEGIN SELECT RAISE(ABORT, 'append-only study events'); END;
            CREATE TABLE IF NOT EXISTS calls(
                call_id INTEGER PRIMARY KEY AUTOINCREMENT, trial_id TEXT NOT NULL,
                role TEXT NOT NULL, reserved INTEGER NOT NULL, charged INTEGER NOT NULL,
                status TEXT NOT NULL, usage TEXT, artifact_hash TEXT);
            CREATE TABLE IF NOT EXISTS artifacts(
                name TEXT PRIMARY KEY, sha256 TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(
                trial_id TEXT NOT NULL, attempt_id TEXT NOT NULL, status TEXT NOT NULL,
                started REAL NOT NULL, finished REAL, failure_category TEXT,
                selection_rule TEXT NOT NULL DEFAULT 'first',
                PRIMARY KEY(trial_id,attempt_id));
            CREATE TABLE IF NOT EXISTS files(
                name TEXT PRIMARY KEY, sha256 TEXT NOT NULL);
        """)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    def _event(self, kind, payload):
        value = {"kind": kind, "time": time.time(), "data": payload}
        row = self.db.execute("SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        previous = row[0] if row else "0" * 64
        checksum = digest({"previous": previous, "payload": value})
        self.db.execute("INSERT INTO events(payload,previous_hash,event_hash) VALUES(?,?,?)",
                        (canonical(value).decode(), previous, checksum))

    def initialize(self, study_id, assignments):
        with self.db:
            self.db.execute("INSERT INTO metadata VALUES('study_id',?)", (study_id,))
            for job in assignments:
                self.db.execute("INSERT INTO trials VALUES(?,?,?,'planned',NULL)",
                                (job.trial_id, job.order, job.model_dump_json()))
            self._event("initialized", {"study_id": study_id, "trials": len(assignments)})

    def verify(self, study_id, assignments):
        identity = self.db.execute("SELECT value FROM metadata WHERE key='study_id'").fetchone()
        if identity is None or identity[0] != study_id:
            raise ValueError("Study database does not match the frozen plan")
        actual = {r["trial_id"]: json.loads(r["assignment"]) for r in self.rows()}
        if actual != {j.trial_id: j.model_dump(mode="json") for j in assignments}:
            raise ValueError("Database assignment projection differs from frozen plan")
        if {r["trial_id"]: r["ordinal"] for r in self.rows()} != {j.trial_id: j.order for j in assignments}:
            raise ValueError("Database dispatch order differs from frozen plan")
        previous = "0" * 64
        states = {j.trial_id: "planned" for j in assignments}
        recorded_outcomes, recorded_artifacts, recorded_files, recorded_calls = {}, {}, {}, {}
        for row in self.db.execute("SELECT * FROM events ORDER BY seq"):
            obj = json.loads(row["payload"])
            if previous != row["previous_hash"] or digest(
                {"previous": previous, "payload": obj}
            ) != row["event_hash"]:
                raise ValueError("Study event chain is invalid")
            previous = row["event_hash"]
            kind, data = obj["kind"], obj["data"]
            if kind in ACTIVE_STATES:
                trial = data["trial_id"]
                if trial not in states or (kind == "running" and states[trial] != "planned") or (
                    kind != "running" and kind not in TRANSITIONS.get(states[trial], set())
                ):
                    raise ValueError("Study event transition is invalid")
                states[trial] = kind
            elif kind == "outcome":
                outcome = TrialOutcome.model_validate(data)
                if states.get(outcome.trial_id) not in ACTIVE_STATES:
                    raise ValueError("Study has an outcome without an active attempt")
                states[outcome.trial_id] = outcome.runtime_status
                recorded_outcomes[outcome.trial_id] = outcome.model_dump(mode="json")
            elif kind == "artifact":
                recorded_artifacts[data["name"]] = data["sha256"]
            elif kind == "file_frozen":
                recorded_files[data["name"]] = data["sha256"]
            elif kind == "call_reserved":
                recorded_calls[data["call_id"]] = {
                    "call_id": data["call_id"], "trial_id": data["trial_id"], "role": data["role"],
                    "reserved": data["output_cap"], "charged": data["output_cap"],
                    "status": "pending", "usage": None, "artifact_hash": None}
            elif kind == "call_finished":
                call = recorded_calls.get(data["call_id"])
                if call is None or call["status"] != "pending":
                    raise ValueError("Model call completed without one unique reservation")
                usage = Usage.model_validate(data["usage"])
                call.update(status=data["status"], usage=usage.model_dump(mode="json"),
                            artifact_hash=data["artifact_hash"],
                            charged=usage.completion_tokens if usage.measured else call["reserved"])
        if {r["trial_id"]: r["status"] for r in self.rows()} != states:
            raise ValueError("Trial state projection differs from transition events")
        if {r["trial_id"]: json.loads(r["outcome"]) for r in self.rows() if r["outcome"]} != recorded_outcomes:
            raise ValueError("Trial outcome projection differs from outcome events")
        if dict(self.db.execute("SELECT name,sha256 FROM artifacts")) != recorded_artifacts:
            raise ValueError("Artifact projection differs from study events")
        if dict(self.db.execute("SELECT name,sha256 FROM files")) != recorded_files:
            raise ValueError("File projection differs from study events")
        calls = {}
        for row in self.db.execute("SELECT * FROM calls"):
            call = dict(row)
            call["usage"] = json.loads(call["usage"]) if call["usage"] else None
            calls[call["call_id"]] = call
        if calls != recorded_calls:
            raise ValueError("Model call projection differs from study events")
        attempts = {r["trial_id"]: r["status"] for r in self.db.execute("SELECT * FROM attempts")}
        if attempts != {trial: state for trial, state in states.items() if state != "planned"}:
            raise ValueError("Attempt history differs from study events")
        for row in self.db.execute("SELECT * FROM artifacts"):
            if digest(json.loads(row["payload"])) != row["sha256"]:
                raise ValueError("Study artifact is corrupt")
        for row in self.db.execute("SELECT * FROM files"):
            path = self.root / row["name"]
            if not path.is_file() or file_hash(path) != row["sha256"]:
                raise ValueError(f"Frozen study artifact changed: {row['name']}")
        for row in self.rows():
            if row["outcome"]:
                outcome = TrialOutcome.model_validate_json(row["outcome"])
                if outcome.trial_id != row["trial_id"] or outcome.runtime_status != row["status"]:
                    raise ValueError("Trial outcome projection is inconsistent")

    def rows(self):
        return list(self.db.execute("SELECT * FROM trials ORDER BY ordinal"))

    def claim(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT * FROM trials WHERE status='planned' ORDER BY ordinal LIMIT 1"
            ).fetchone()
            if row:
                self.db.execute("UPDATE trials SET status='running' WHERE trial_id=?", (row["trial_id"],))
                self.db.execute("INSERT INTO attempts(trial_id,attempt_id,status,started) "
                                "VALUES(?,'attempt-001','running',?)", (row["trial_id"], time.time()))
                self._event("running", {"trial_id": row["trial_id"], "attempt_id": "attempt-001"})
            self.db.commit()
            return json.loads(row["assignment"]) if row else None
        except Exception:
            self.db.rollback()
            raise

    def transition(self, trial_id, state, payload=None):
        with self.db:
            row = self.db.execute("SELECT status FROM trials WHERE trial_id=?", (trial_id,)).fetchone()
            if row is None or state not in TRANSITIONS.get(row[0], set()):
                raise ValueError(f"Invalid trial transition to {state}")
            self.db.execute("UPDATE trials SET status=? WHERE trial_id=?", (state, trial_id))
            self.db.execute("UPDATE attempts SET status=? WHERE trial_id=? AND attempt_id='attempt-001'",
                            (state, trial_id))
            self._event(state, {**(payload or {}), "trial_id": trial_id})

    def finish(self, outcome):
        outcome = TrialOutcome.model_validate(outcome)
        with self.db:
            row = self.db.execute("SELECT status,outcome FROM trials WHERE trial_id=?",
                                  (outcome.trial_id,)).fetchone()
            if row is None or row[0] not in ACTIVE_STATES:
                if row and row[1] and json.loads(row[1]) == outcome.model_dump(mode="json"):
                    return
                raise ValueError("Only an active attempt may record its first terminal outcome")
            self.db.execute("UPDATE trials SET status=?,outcome=? WHERE trial_id=?",
                            (outcome.runtime_status, outcome.model_dump_json(), outcome.trial_id))
            self.db.execute("UPDATE attempts SET status=?,finished=?,failure_category=? "
                            "WHERE trial_id=? AND attempt_id=?", (outcome.runtime_status, time.time(),
                             outcome.failure_category, outcome.trial_id, outcome.attempt_id))
            self._event("outcome", outcome.model_dump(mode="json"))

    def recover_interrupted(self):
        # Called only while holding the coordinator lock. Never rerun an actor attempt.
        for row in self.rows():
            if row["status"] not in ACTIVE_STATES:
                continue
            directory = self.root / "trials" / row["trial_id"] / "attempt-001"
            outcome = self.artifact(f"outcome/{row['trial_id']}")
            if outcome:
                self.finish(outcome)
                continue
            recovered = TrialOutcome(trial_id=row["trial_id"], runtime_status="interrupted",
                failure_category="coordinator_interrupted", error="Coordinator interrupted; actor not rerun")
            snapshots = list(self.db.execute(
                "SELECT payload FROM artifacts WHERE name LIKE ? ORDER BY name DESC",
                (f"snapshot/{row['trial_id']}/%",)))
            frozen = self.artifact(f"final/{row['trial_id']}")
            snapshot = frozen or (json.loads(snapshots[0][0]) if snapshots else None)
            if snapshot:
                patch = (self.root / snapshot["path"]).read_text()
                if digest(patch) != snapshot["patch_hash"]:
                    raise ValueError("Recovery snapshot hash mismatch")
                # Only use a committed snapshot; never inspect a possibly partial workspace.
                write_text(directory / "final.patch", patch)
                self.freeze_file(directory / "final.patch")
                recovered.final_patch_hash = snapshot["patch_hash"]
                recovered.final_tree_hash = snapshot["tree_hash"]
            draft = self.artifact(f"draft/{row['trial_id']}")
            if draft:
                recovered.draft_patch_hash = draft["patch_hash"]
                recovered.draft_tree_hash = draft["tree_hash"]
            write_json(directory / "outcome.json", recovered.model_dump(mode="json"))
            self.freeze_file(directory / "outcome.json")
            self.put_artifact(f"outcome/{row['trial_id']}", recovered.model_dump(mode="json"))
            self.finish(recovered)

    def append_event(self, kind, payload):
        with self.db:
            self._event(kind, payload)

    def freeze_file(self, path):
        path = Path(path).resolve()
        name = path.relative_to(self.root.resolve()).as_posix()
        checksum = file_hash(path)
        with self.db:
            existing = self.db.execute("SELECT sha256 FROM files WHERE name=?", (name,)).fetchone()
            if existing:
                if existing[0] != checksum:
                    raise ValueError("Cannot replace a frozen artifact")
                return checksum
            self.db.execute("INSERT INTO files VALUES(?,?)", (name, checksum))
            self._event("file_frozen", {"name": name, "sha256": checksum})
        return checksum

    def put_artifact(self, name, payload):
        checksum = digest(payload)
        with self.db:
            self.db.execute("INSERT INTO artifacts VALUES(?,?,?)",
                            (name, checksum, canonical(payload).decode()))
            self._event("artifact", {"name": name, "sha256": checksum})

    def artifact(self, name):
        row = self.db.execute("SELECT payload FROM artifacts WHERE name=?", (name,)).fetchone()
        return json.loads(row[0]) if row else None

    def reserve_call(self, trial_id, role, cap, spec):
        if not isinstance(cap, int) or cap <= 0:
            raise ValueError("Model call requires a positive integer output reservation")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            calls, charged = self.db.execute(
                "SELECT COUNT(*),COALESCE(SUM(charged),0) FROM calls"
            ).fetchone()
            if calls + 1 > spec.max_model_calls or charged + cap > spec.max_completion_tokens:
                raise StudyBudgetExceeded("Frozen study call/completion reservation cap exhausted")
            cursor = self.db.execute(
                "INSERT INTO calls(trial_id,role,reserved,charged,status) VALUES(?,?,?,?,'pending')",
                (trial_id, role, cap, cap))
            call_id = cursor.lastrowid
            self._event("call_reserved", {"call_id": call_id, "trial_id": trial_id,
                                          "role": role, "output_cap": cap})
            self.db.commit()
            return call_id
        except Exception:
            self.db.rollback()
            raise

    def finish_call(self, call_id, usage, artifact_hash, status):
        usage = Usage.model_validate(usage)
        with self.db:
            row = self.db.execute("SELECT reserved,status FROM calls WHERE call_id=?", (call_id,)).fetchone()
            if not row or row[1] != "pending":
                raise ValueError("Call result already recorded or reservation missing")
            charge = usage.completion_tokens if usage.measured else row[0]
            self.db.execute("UPDATE calls SET charged=?,status=?,usage=?,artifact_hash=? WHERE call_id=?",
                            (charge, status, usage.model_dump_json(), artifact_hash, call_id))
            self._event("call_finished", {"call_id": call_id, "status": status,
                                          "usage": usage.model_dump(), "artifact_hash": artifact_hash})

    def usage(self, trial_id=None):
        sql = "SELECT * FROM calls" + (" WHERE trial_id=?" if trial_id else "")
        groups = {}
        for row in self.db.execute(sql, (trial_id,) if trial_id else ()):
            group = groups.setdefault(row["role"], {"calls": 0, "prompt_tokens": 0,
                "completion_tokens": 0, "seconds": 0.0, "unknown_calls": 0,
                "reserved_or_measured_completion_tokens": 0})
            group["calls"] += 1
            group["reserved_or_measured_completion_tokens"] += row["charged"]
            usage = json.loads(row["usage"]) if row["usage"] else {"measured": False}
            group["unknown_calls"] += int(not usage["measured"])
            for key in ("prompt_tokens", "completion_tokens", "seconds"):
                group[key] += usage.get(key, 0)
        return groups


class MeteredModel:
    """Persist every attempted request before sending it; no automatic inference retries."""
    def __init__(self, model, db, spec, trial_id, role, identity):
        self.model, self.db, self.spec = model, db, spec
        self.trial_id, self.role, self.identity = trial_id, role, identity
        self.last_call_id = None

    def complete(self, system, user, *, max_tokens, timeout_seconds):
        cap = min(max_tokens, self.model.config.max_tokens)
        call_id = self.db.reserve_call(self.trial_id, self.role, cap, self.spec)
        self.last_call_id = call_id
        path = self.db.root / "calls" / f"{call_id:08d}.json"
        messages = {"system": system, "user": user}
        safe = {k: redact(v) for k, v in messages.items()}
        artifact = {"call_id": call_id, "trial_id": self.trial_id, "role": self.role,
                    "model": self.identity, "messages": safe, "prompt_hash": digest(messages),
                    "redacted": safe != messages, "output_cap": cap, "status": "pending"}
        write_json(path.with_suffix(".request.json"), artifact)
        self.db.freeze_file(path.with_suffix(".request.json"))
        start = time.monotonic()
        usage, error = Usage(measured=False), None
        try:
            raw, usage = self.model.complete(system, user, max_tokens=cap,
                                             timeout_seconds=timeout_seconds)
            artifact.update(response=redact(raw), response_hash=digest(raw), status="completed")
            if usage.completion_tokens > cap:
                raise RuntimeError("Provider exceeded the requested output cap")
            return raw, usage
        except BaseException as exc:
            error = exc
            usage = getattr(exc, "usage", usage)
            if not hasattr(exc, "usage"):
                exc.usage = usage
            artifact.update(status="error", error=redact(f"{type(exc).__name__}: {exc}"),
                            response=redact(getattr(exc, "raw", "")))
            raise
        finally:
            usage.seconds = time.monotonic() - start
            artifact["usage"] = usage.model_dump(mode="json")
            write_json(path, artifact)
            self.db.freeze_file(path)
            self.db.finish_call(call_id, usage, digest(artifact), "error" if error else "completed")
