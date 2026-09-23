import json
import os
import sqlite3
from pathlib import Path

from .io import canonical, digest, file_hash, write_json, write_jsonl
from .schema import StepRecord


class EventStore:
    """Append-only SQLite event ledger; exported hashes detect later tampering.

    Local database owners can change files. Anchor manifests externally for stronger immutability.
    """

    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS events (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
              payload TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS immutable_update BEFORE UPDATE ON events
              BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_delete BEFORE DELETE ON events
              BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
        """)

    def append(self, record: StepRecord):
        payload = StepRecord.model_validate(record.model_dump(mode="json")).model_dump(mode="json")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute(
                "SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            previous = row[0] if row else "0" * 64
            event_hash = digest({"previous": previous, "payload": payload})
            self.db.execute(
                "INSERT INTO events(event_id,payload,previous_hash,event_hash) VALUES(?,?,?,?)",
                (record.event_id, canonical(payload).decode(), previous, event_hash),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def records(self):
        previous = "0" * 64
        for payload, prev, actual in self.db.execute(
            "SELECT payload, previous_hash, event_hash FROM events ORDER BY seq"
        ):
            obj = json.loads(payload)
            if prev != previous or digest({"previous": prev, "payload": obj}) != actual:
                raise ValueError("Event ledger hash-chain integrity failure")
            yield StepRecord.model_validate(obj)
            previous = actual

    def close(self):
        self.db.close()


def export_ledger(database, output, encrypt_env=None):
    import pyarrow as pa
    import pyarrow.parquet as pq

    if not Path(database).is_file():
        raise ValueError(f"No event database exists at {database}")
    cipher = None
    if encrypt_env:
        from cryptography.fernet import Fernet

        key = os.environ.get(encrypt_env)
        if not key:
            raise ValueError(f"Encryption key missing from {encrypt_env}")
        cipher = Fernet(key.encode())
    output = Path(output)
    if (output / "manifest.json").exists():
        raise ValueError("Export exists; use a new directory to preserve immutable artifacts")
    output.mkdir(parents=True, exist_ok=True)
    store = EventStore(database)
    count = 0
    schema = pa.schema(
        [
            ("event_id", pa.string()),
            ("task_id", pa.string()),
            ("split", pa.string()),
            ("record_json", pa.string()),
        ]
    )
    try:
        with pq.ParquetWriter(output / "events.parquet", schema, compression="zstd") as writer:

            def rows():
                nonlocal count
                batch = []
                for record in store.records():
                    obj = record.model_dump(mode="json")
                    count += 1
                    batch.append(
                        {
                            "event_id": record.event_id,
                            "task_id": record.task_id,
                            "split": record.split,
                            "record_json": canonical(obj).decode(),
                        }
                    )
                    if len(batch) >= 1000:
                        writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                        batch.clear()
                    yield obj
                if batch:
                    writer.write_table(pa.Table.from_pylist(batch, schema=schema))

            write_jsonl(output / "events.jsonl", rows())
    finally:
        store.close()
    files = {}
    for filename in ("events.jsonl", "events.parquet"):
        path = output / filename
        if encrypt_env:
            encrypted = path.with_suffix(path.suffix + ".fernet")
            encrypted.write_bytes(cipher.encrypt(path.read_bytes()))
            path.unlink()
            path = encrypted
        files[path.name] = file_hash(path)
    result = {
        "schema_version": 1,
        "rows": count,
        "files": files,
        "encrypted": bool(encrypt_env),
        "source": str(database),
    }
    write_json(output / "manifest.json", result)
    return result


def verify_export(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    for filename, expected in manifest["files"].items():
        if file_hash(directory / filename) != expected:
            raise ValueError(f"Export checksum failed: {filename}")
    return manifest
