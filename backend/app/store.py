"""Persistent event store (SQLite) with a local SHA-256 hash chain.

Every record (sensor snapshot, model output, risk decision, human action, simulated drone step)
is appended to `events`. Each event stores the hash of the previous one, so any later change
breaks the chain and is detected by `verify_chain()`. This is local integrity only; anchoring
the chain on Hedera is planned and shown as "pending".
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "aeroguard.db"
GENESIS = "0" * 64

SOURCES = {"sensor", "model", "risk", "human", "system", "simulated"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  wall_ts TEXT NOT NULL,
  data_ts TEXT,
  kind TEXT NOT NULL,
  source TEXT NOT NULL,
  actor TEXT,
  case_id TEXT,
  payload TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_case ON events(case_id);
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY,
  data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
  kind TEXT NOT NULL,
  id TEXT NOT NULL,
  data TEXT NOT NULL,
  PRIMARY KEY (kind, id)
);
"""


def _canonical(d: dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str)


class Store:
    def __init__(self, path: Path | str = DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)

    # ------------------------------------------------------------------ events
    def append(self, kind: str, source: str, payload: dict, *, data_ts=None, actor=None, case_id=None) -> dict:
        if source not in SOURCES:
            raise ValueError(f"unknown source {source!r}")
        with self._lock:
            row = self._db.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            prev = row["hash"] if row else GENESIS
            rec = {"wall_ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                   "data_ts": str(data_ts) if data_ts is not None else None, "kind": kind, "source": source,
                   "actor": actor, "case_id": case_id, "payload": payload}
            h = hashlib.sha256((prev + _canonical(rec)).encode()).hexdigest()
            cur = self._db.execute(
                "INSERT INTO events (wall_ts,data_ts,kind,source,actor,case_id,payload,prev_hash,hash) VALUES (?,?,?,?,?,?,?,?,?)",
                (rec["wall_ts"], rec["data_ts"], kind, source, actor, case_id, _canonical(payload), prev, h))
            self._db.commit()
            return {**rec, "seq": cur.lastrowid, "prev_hash": prev, "hash": h}

    def events(self, case_id: str | None = None, kinds: list[str] | None = None, limit: int = 1000) -> list[dict]:
        q, args = "SELECT * FROM events", []
        where = []
        if case_id:
            where.append("case_id = ?"); args.append(case_id)
        if kinds:
            where.append(f"kind IN ({','.join('?' * len(kinds))})"); args += kinds
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY seq DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._db.execute(q, args).fetchall()
        return [self._row(r) for r in reversed(rows)]

    @staticmethod
    def _row(r) -> dict:
        d = dict(r)
        d["payload"] = json.loads(d["payload"])
        return d

    def hash_at(self, seq: int) -> str | None:
        """Recompute the chain from the start up to event `seq`; None if it is broken or missing."""
        with self._lock:
            rows = self._db.execute("SELECT * FROM events WHERE seq <= ? ORDER BY seq", (seq,)).fetchall()
        prev = GENESIS
        for r in rows:
            rec = {"wall_ts": r["wall_ts"], "data_ts": r["data_ts"], "kind": r["kind"], "source": r["source"],
                   "actor": r["actor"], "case_id": r["case_id"], "payload": json.loads(r["payload"])}
            h = hashlib.sha256((prev + _canonical(rec)).encode()).hexdigest()
            if r["prev_hash"] != prev or r["hash"] != h:
                return None
            prev = h
        return prev if rows and rows[-1]["seq"] == seq else None

    def verify_chain(self) -> dict:
        with self._lock:
            rows = self._db.execute("SELECT * FROM events ORDER BY seq").fetchall()
        prev = GENESIS
        for r in rows:
            rec = {"wall_ts": r["wall_ts"], "data_ts": r["data_ts"], "kind": r["kind"], "source": r["source"],
                   "actor": r["actor"], "case_id": r["case_id"], "payload": json.loads(r["payload"])}
            h = hashlib.sha256((prev + _canonical(rec)).encode()).hexdigest()
            if r["prev_hash"] != prev or r["hash"] != h:
                return {"ok": False, "events": len(rows), "broken_at_seq": r["seq"]}
            prev = h
        return {"ok": True, "events": len(rows), "head": prev}

    # ------------------------------------------------------------------ cases
    def save_case(self, case: dict) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO cases (id, data) VALUES (?, ?)", (case["id"], _canonical(case)))
            self._db.commit()

    def get_case(self, case_id: str) -> dict | None:
        with self._lock:
            r = self._db.execute("SELECT data FROM cases WHERE id = ?", (case_id,)).fetchone()
        return json.loads(r["data"]) if r else None

    def cases(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT data FROM cases").fetchall()
        return sorted((json.loads(r["data"]) for r in rows), key=lambda c: c["opened_wall_ts"], reverse=True)

    # ------------------------------------------------------------------ generic records (missions, findings, schedules)
    def put_record(self, kind: str, rec: dict) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO records (kind, id, data) VALUES (?, ?, ?)", (kind, rec["id"], _canonical(rec)))
            self._db.commit()

    def get_record(self, kind: str, rid: str) -> dict | None:
        with self._lock:
            r = self._db.execute("SELECT data FROM records WHERE kind = ? AND id = ?", (kind, rid)).fetchone()
        return json.loads(r["data"]) if r else None

    def list_records(self, kind: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT data FROM records WHERE kind = ?", (kind,)).fetchall()
        return [json.loads(r["data"]) for r in rows]

    def reset(self) -> None:
        with self._lock:
            self._db.executescript("DELETE FROM events; DELETE FROM cases; DELETE FROM records; DELETE FROM sqlite_sequence;")
            self._db.commit()
