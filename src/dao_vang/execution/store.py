"""Single-worker order journal with durable intents and a web command inbox."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .contracts import canonical, utc_now


class ExecutionStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, payload TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS signals(id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS trades(id TEXT PRIMARY KEY, symbol TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS journal(seq INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS ledger(id TEXT PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS journal_kind_at ON journal(kind,at);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key: str, default=None) -> Any:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key: str, value):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO state VALUES (?,?)", (key, canonical(value))
            )

    def record(self, kind: str, value):
        with self.connect() as db:
            db.execute(
                "INSERT INTO journal(at,kind,payload) VALUES (?,?,?)",
                (utc_now().isoformat(), kind, canonical(value)),
            )

    def signal(self, signal):
        payload = signal.model_dump(mode="json")
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO signals VALUES (?,?,?)",
                (signal.source_id, canonical(payload), "pending"),
            )

    def pending(self):
        with self.connect() as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT payload FROM signals WHERE status='pending' ORDER BY rowid"
                )
            ]

    def finish_signal(self, identity, reason):
        with self.connect() as db:
            db.execute("UPDATE signals SET status=? WHERE id=?", (reason, identity))
        self.record("signal_decision", {"id": identity, "reason": reason})

    def trades(self, active_only=True):
        query = "SELECT payload FROM trades"
        if active_only:
            query += " WHERE status NOT IN ('closed','rejected')"
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute(query)]

    def trade(self, value):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO trades VALUES (?,?,?,?)",
                (value["id"], value["symbol"], value["status"], canonical(value)),
            )
            db.execute(
                "INSERT INTO journal(at,kind,payload) VALUES (?,?,?)",
                (utc_now().isoformat(), "trade", canonical(value)),
            )

    def enqueue(self, action, payload):
        identity = uuid.uuid4().hex
        with self.connect() as db:
            db.execute(
                "INSERT INTO commands VALUES (?,?,?,?,?)",
                (
                    identity,
                    utc_now().isoformat(),
                    action,
                    canonical(payload),
                    "pending",
                ),
            )
        return identity

    def commands(self):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM commands WHERE status='pending' ORDER BY at"
                )
            ]

    def complete_command(self, identity, status):
        with self.connect() as db:
            db.execute("UPDATE commands SET status=? WHERE id=?", (status, identity))
        self.record("command_result", {"command_id": identity, "status": status})

    def money_event(self, identity, at, kind, payload):
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO ledger VALUES (?,?,?,?)",
                (identity, at, kind, canonical(payload)),
            )

    def history(self, limit=100):
        with self.connect() as db:
            return [
                {**dict(r), "payload": json.loads(r["payload"])}
                for r in db.execute(
                    "SELECT * FROM journal ORDER BY seq DESC LIMIT ?", (limit,)
                )
            ]

    def backup(self, destination: Path):
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
