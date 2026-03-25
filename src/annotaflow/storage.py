"""Append-only audit actions and versioned adjudication decisions."""
import json
import sqlite3
from pathlib import Path

from .io import utc_now


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, action TEXT NOT NULL,
                record_id TEXT, actor TEXT, payload TEXT NOT NULL)""")
            con.execute("""CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL,
                label TEXT, status TEXT NOT NULL CHECK(status IN ('resolved','unresolved')),
                rationale TEXT NOT NULL, reviewer TEXT NOT NULL,
                guideline_version TEXT NOT NULL, at TEXT NOT NULL)""")
            con.execute("""CREATE TABLE IF NOT EXISTS imports (
                project_id INTEGER NOT NULL, record_id TEXT NOT NULL,
                task_id INTEGER NOT NULL, payload_hash TEXT NOT NULL,
                PRIMARY KEY (project_id, record_id))""")

    def _db(self):
        return sqlite3.connect(self.path)

    def event(self, action, record_id=None, actor=None, payload=None):
        with self._db() as c:
            c.execute("INSERT INTO events (at,action,record_id,actor,payload) VALUES (?,?,?,?,?)",
                      (utc_now(), action, record_id, actor, json.dumps(payload or {}, sort_keys=True)))

    def decide(self, record_id, label, rationale, reviewer, version):
        if not reviewer.strip():
            raise ValueError("Reviewer identity required")
        if not rationale.strip():
            raise ValueError("Decision rationale required (including unresolved decisions)")
        status = "resolved" if label is not None else "unresolved"
        at = utc_now()
        with self._db() as c:
            c.execute("""INSERT INTO decisions
                (record_id,label,status,rationale,reviewer,guideline_version,at)
                VALUES(?,?,?,?,?,?,?)""",
                (record_id, label, status, rationale, reviewer, version, at))
        self.event("adjudication", record_id, reviewer, {"status": status, "label": label, "version": version})

    def latest_decisions(self):
        with self._db() as c:
            rows = c.execute("""SELECT d.record_id,d.label,d.status,d.rationale,d.reviewer,
                     d.guideline_version,d.at,d.id FROM decisions d
                     JOIN (SELECT record_id,MAX(id) mid FROM decisions GROUP BY record_id) x
                     ON d.id=x.mid""").fetchall()
        return {r[0]: dict(zip(["record_id", "label", "status", "rationale", "reviewer",
                                "guideline_version", "at", "revision"], r)) for r in rows}

    def decision_history(self):
        with self._db() as c:
            rows = c.execute("SELECT record_id,label,status,rationale,reviewer,guideline_version,at,id FROM decisions ORDER BY id").fetchall()
        return [dict(zip(["record_id", "label", "status", "rationale", "reviewer",
                          "guideline_version", "at", "revision"], r)) for r in rows]

    def import_map(self, project_id):
        with self._db() as c:
            rows = c.execute("SELECT record_id,task_id,payload_hash FROM imports WHERE project_id=?", (project_id,)).fetchall()
        return {r[0]: {"task_id": r[1], "payload_hash": r[2]} for r in rows}

    def remember_import(self, project_id, record_id, task_id, payload_hash):
        with self._db() as c:
            c.execute("INSERT INTO imports VALUES(?,?,?,?)", (project_id, record_id, task_id, payload_hash))
