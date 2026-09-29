"""SQLite registry of hosts, runs, events and studies (WAL, safe for several processes).

Tables mirror pydelling-cloud's ``Job``/``JobEvent``/``SimulationRun`` so a later
migration is a column mapping. Every write bumps a global ``rev``; readers stream
rows with ``rev > cursor`` (``changes``), including rows written by other processes.
"""

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

CLIENT_PHASES = ("queued", "preflight", "deploying", "starting")
TERMINAL = ("completed", "failed", "cancelled", "interrupted", "lost", "missing")
ACTIVE = (*CLIENT_PHASES, "running", "cancelling")
FINISHED_STUDIES = ("completed", "failed", "interrupted")
SERIES_MAX = 256
LOG_TAIL_MAX = 65536

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
INSERT OR IGNORE INTO meta VALUES ('rev', 0);
CREATE TABLE IF NOT EXISTS deleted_runs (
  id TEXT PRIMARY KEY, host_id TEXT NOT NULL, remote_folder TEXT NOT NULL,
  rev INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_deleted_folder ON deleted_runs (host_id, remote_folder);
CREATE TABLE IF NOT EXISTS hosts (
  id TEXT PRIMARY KEY, label TEXT, transport TEXT NOT NULL, ssh TEXT, root TEXT, uv TEXT,
  options_json TEXT, stream_state TEXT NOT NULL DEFAULT 'offline', stream_error TEXT,
  heartbeat_json TEXT, hello_json TEXT, updated_at REAL, rev INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, host_id TEXT NOT NULL, name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'campaign', entry_id TEXT, entry_path TEXT, argv_json TEXT,
  remote_folder TEXT NOT NULL, local_folder TEXT, status TEXT NOT NULL DEFAULT 'queued',
  phase TEXT, progress REAL, counts_json TEXT, release_id TEXT, worker_json TEXT,
  worker_alive INTEGER, exit_code INTEGER, campaign_json TEXT, config_json TEXT,
  preview_json TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0,
  launch_failed INTEGER NOT NULL DEFAULT 0, error TEXT, origin TEXT NOT NULL DEFAULT 'cli',
  event_offset INTEGER NOT NULL DEFAULT 0, log_offset INTEGER NOT NULL DEFAULT 0,
  log_tail TEXT, remote_mtime REAL, launcher_pid INTEGER, created_at REAL NOT NULL,
  started_at REAL, finished_at REAL, updated_at REAL NOT NULL,
  rev INTEGER NOT NULL DEFAULT 0, UNIQUE (host_id, remote_folder));
CREATE INDEX IF NOT EXISTS ix_runs_rev ON runs (rev);
CREATE TABLE IF NOT EXISTS run_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES runs (id) ON DELETE CASCADE, ts REAL NOT NULL,
  source TEXT NOT NULL, event_type TEXT NOT NULL, level TEXT NOT NULL DEFAULT 'info',
  message TEXT, payload_json TEXT, remote_offset INTEGER,
  UNIQUE (run_id, source, remote_offset));
CREATE INDEX IF NOT EXISTS ix_run_events_run ON run_events (run_id, id);
CREATE TABLE IF NOT EXISTS studies (
  run_id TEXT NOT NULL REFERENCES runs (id) ON DELETE CASCADE, name TEXT NOT NULL,
  kind TEXT, state TEXT, attempt INTEGER, started REAL, finished REAL, runtime_s REAL,
  returncode INTEGER, error TEXT, workdir TEXT, sim_time_s REAL, final_time_s REAL,
  progress REAL, dt_s REAL, step INTEGER, cuts INTEGER, newton INTEGER, wall_s REAL,
  unit TEXT, series_json TEXT, updated_at REAL, rev INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (run_id, name));
CREATE INDEX IF NOT EXISTS ix_studies_rev ON studies (rev);
"""
SCHEMA_VERSION = 2


def decode(row):
    if row is None:
        return None
    result = dict(row)
    for key, value in result.items():
        if key.endswith("_json") and isinstance(value, str):
            result[key] = json.loads(value)
    return result


def encode(fields):
    return {
        key: json.dumps(value, sort_keys=True, default=str)
        if key.endswith("_json") and value is not None
        else value
        for key, value in fields.items()
    }


def derive_status(run):
    """Run status from client phase + remote facts (worker liveness, exit, campaign)."""
    status = run.get("status") or "queued"
    campaign = (run.get("campaign_json") or {}).get("state")
    cancel = bool(run.get("cancel_requested"))
    if run.get("worker_alive"):
        return "cancelling" if cancel else "running"
    if run.get("launch_failed"):
        return status if status in ("failed", "cancelled") else "failed"
    if status in CLIENT_PHASES:
        return status
    exit_code = run.get("exit_code")
    if exit_code is not None:
        if exit_code == 0:
            return campaign if campaign in TERMINAL else "completed"
        return "cancelled" if cancel or campaign == "cancelled" else "failed"
    if campaign in TERMINAL:
        return campaign
    if status == "cancelling" and run.get("worker_alive") is not None:
        return "cancelled"
    if campaign == "running" or run.get("worker_json"):
        return "lost"
    return status


def merge_series(old, new):
    merged = {}
    for point in [*(old or []), *(new or [])]:
        merged[float(point[0])] = list(point)
    points = [merged[t] for t in sorted(merged)]
    if len(points) > SERIES_MAX:
        step = (len(points) - 1) / (SERIES_MAX - 1)
        points = [points[round(i * step)] for i in range(SERIES_MAX)]
    return points


class Registry:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        # executescript() commits on its own; idempotent DDL needs no explicit transaction.
        self.db.executescript(SCHEMA)
        self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @property
    def db(self):
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA busy_timeout = 30000")
            connection.execute("PRAGMA foreign_keys = ON")
            self._local.connection = connection
        return connection

    def journal_mode(self):
        return self.db.execute("PRAGMA journal_mode").fetchone()[0]

    @contextmanager
    def _write(self):
        db = self.db
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
        except BaseException:
            db.execute("ROLLBACK")
            raise
        db.execute("COMMIT")

    @staticmethod
    def _bump(db):
        db.execute("UPDATE meta SET value = value + 1 WHERE key = 'rev'")
        return db.execute("SELECT value FROM meta WHERE key = 'rev'").fetchone()[0]

    def last_event_id(self):
        return self.db.execute("SELECT COALESCE(MAX(id), 0) FROM run_events").fetchone()[0]

    def current_rev(self):
        return self.db.execute("SELECT value FROM meta WHERE key = 'rev'").fetchone()[0]

    # Hosts -----------------------------------------------------------------------------
    def upsert_host(self, host):
        fields = {
            "id": host["id"],
            "label": host.get("label") or host["id"],
            "transport": host.get("transport", "ssh"),
            "ssh": host.get("ssh"),
            "root": host.get("root"),
            "uv": host.get("uv"),
            "options_json": host.get("options") or {},
        }
        with self._write() as db:
            fields.update(rev=self._bump(db), updated_at=time.time())
            fields = encode(fields)
            columns = ", ".join(fields)
            updates = ", ".join(f"{k} = excluded.{k}" for k in fields if k != "id")
            db.execute(
                f"INSERT INTO hosts ({columns}) VALUES ({', '.join('?' * len(fields))}) "
                f"ON CONFLICT (id) DO UPDATE SET {updates}",
                list(fields.values()),
            )

    def set_host_stream(self, host_id, state, error=None, heartbeat=None, hello=None):
        fields = {"stream_state": state, "stream_error": error}
        if heartbeat is not None:
            fields["heartbeat_json"] = heartbeat
        if hello is not None:
            fields["hello_json"] = hello
        self._update("hosts", "id = ?", [host_id], fields)

    def list_hosts(self):
        return [decode(r) for r in self.db.execute("SELECT * FROM hosts ORDER BY id")]

    def get_host(self, host_id):
        return decode(self.db.execute("SELECT * FROM hosts WHERE id = ?", [host_id]).fetchone())

    def _update(self, table, where, args, fields):
        with self._write() as db:
            fields = encode({**fields, "rev": self._bump(db), "updated_at": time.time()})
            assignments = ", ".join(f"{k} = ?" for k in fields)
            db.execute(f"UPDATE {table} SET {assignments} WHERE {where}", [*fields.values(), *args])

    # Runs ------------------------------------------------------------------------------
    def ensure_run(self, host_id, remote_folder, **fields):
        """Get or create the run identified by (host, remote folder); update ``fields``."""
        with self._write() as db:
            if (
                fields.get("origin") == "discovered"
                and db.execute(
                    "SELECT 1 FROM deleted_runs WHERE host_id = ? AND remote_folder = ?",
                    [host_id, remote_folder],
                ).fetchone()
            ):
                return None
            row = db.execute(
                "SELECT id FROM runs WHERE host_id = ? AND remote_folder = ?",
                [host_id, remote_folder],
            ).fetchone()
            if row is None:
                run_id = fields.pop("id", None) or uuid.uuid4().hex
                now = time.time()
                values = encode(
                    {
                        "name": Path(remote_folder).name,
                        **fields,
                        "id": run_id,
                        "host_id": host_id,
                        "remote_folder": remote_folder,
                        "created_at": now,
                        "updated_at": now,
                        "rev": self._bump(db),
                    }
                )
                db.execute(
                    f"INSERT INTO runs ({', '.join(values)}) "
                    f"VALUES ({', '.join('?' * len(values))})",
                    list(values.values()),
                )
                return run_id
            run_id = row["id"]
        fields.pop("id", None)
        if fields:
            self.update_run(run_id, **fields)
        return run_id

    def delete_runs(self, run_id=None, *, before_delete=None):
        """Delete history atomically; retain identifiers to suppress rediscovery.

        Passing no id clears inactive runs, without the list endpoint's pagination.
        Active workers must be stopped before removing their history.
        """
        with self._write() as db:
            rows = db.execute(
                "SELECT * FROM runs" + (" WHERE id = ?" if run_id else ""),
                [run_id] if run_id else [],
            ).fetchall()
            inactive = [r for r in rows if r["status"] not in ACTIVE and not r["worker_alive"]]
            if run_id and len(inactive) != len(rows):
                raise ValueError("El run sigue activo; cancélalo y espera a que termine antes de borrar")
            if rows and not inactive:
                raise ValueError("Todos los runs siguen activos; no hay historial inactivo que borrar")
            rows = inactive
            if not rows:
                return []
            if before_delete is not None:
                before_delete([dict(r) for r in rows])
            rev = self._bump(db)
            db.executemany(
                "INSERT OR REPLACE INTO deleted_runs (id, host_id, remote_folder, rev) "
                "VALUES (?, ?, ?, ?)",
                [(r["id"], r["host_id"], r["remote_folder"], rev) for r in rows],
            )
            db.executemany("DELETE FROM runs WHERE id = ?", [(r["id"],) for r in rows])
            return [r["id"] for r in rows]

    def update_run(self, run_id, **fields):
        if not fields:
            return
        if "status" in fields:
            current = self.get_run(run_id) or {}
            status = fields["status"]
            if status not in ("queued", "prepared", "unknown") and not current.get("started_at"):
                fields.setdefault("started_at", time.time())
            if status in TERMINAL and current.get("status") not in TERMINAL:
                fields.setdefault("finished_at", time.time())
            elif status not in TERMINAL:
                fields.setdefault("finished_at", None)
        self._update("runs", "id = ?", [run_id], fields)

    def get_run(self, run_id):
        return decode(self.db.execute("SELECT * FROM runs WHERE id = ?", [run_id]).fetchone())

    def find_run(self, host_id, remote_folder):
        return decode(
            self.db.execute(
                "SELECT * FROM runs WHERE host_id = ? AND remote_folder = ?",
                [host_id, remote_folder],
            ).fetchone()
        )

    def list_runs(self, *, status=None, host=None, q=None, active=False, limit=200, offset=0):
        where, args = [], []
        if status:
            where.append("status = ?")
            args.append(status)
        if host:
            where.append("host_id = ?")
            args.append(host)
        if q:
            where.append("(name LIKE ? OR entry_path LIKE ? OR remote_folder LIKE ?)")
            args.extend([f"%{q}%"] * 3)
        if active:
            where.append(f"status IN ({', '.join('?' * len(ACTIVE))})")
            args.extend(ACTIVE)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self.db.execute(
            "SELECT id, host_id, name, kind, entry_id, entry_path, remote_folder, local_folder, "
            "status, phase, progress, counts_json, worker_alive, exit_code, error, origin, "
            "cancel_requested, created_at, started_at, finished_at, updated_at, rev "
            f"FROM runs {clause} ORDER BY COALESCE(started_at, created_at) DESC "
            "LIMIT ? OFFSET ?",
            [*args, int(limit), int(offset)],
        )
        return [decode(r) for r in rows]

    def known(self, host_id):
        """Offsets and mtimes already stored for ``host_id`` (sent to the watcher)."""
        rows = self.db.execute(
            "SELECT remote_folder, remote_mtime, event_offset, log_offset FROM runs "
            "WHERE host_id = ?",
            [host_id],
        )
        return {
            r["remote_folder"]: {
                "mtime": r["remote_mtime"],
                "event_offset": r["event_offset"],
                "log_offset": r["log_offset"],
            }
            for r in rows
        }

    def append_log(self, run_id, text, offset_end):
        run = self.get_run(run_id) or {}
        tail = ((run.get("log_tail") or "") + text)[-LOG_TAIL_MAX:]
        self.update_run(run_id, log_tail=tail, log_offset=int(offset_end))

    # Events ----------------------------------------------------------------------------
    def add_event(
        self,
        run_id,
        event_type,
        *,
        source="client",
        level="info",
        message=None,
        payload=None,
        remote_offset=None,
        ts=None,
    ):
        with self._write() as db:
            if not db.execute("SELECT 1 FROM runs WHERE id = ?", [run_id]).fetchone():
                return False
            cursor = db.execute(
                "INSERT OR IGNORE INTO run_events (run_id, ts, source, event_type, level, "
                "message, payload_json, remote_offset) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    run_id,
                    ts if ts is not None else time.time(),
                    source,
                    event_type,
                    level,
                    message,
                    json.dumps(payload, sort_keys=True, default=str) if payload else None,
                    remote_offset,
                ],
            )
            return cursor.rowcount == 1

    def events(self, run_id, after=0, limit=500):
        rows = self.db.execute(
            "SELECT * FROM run_events WHERE run_id = ? AND id > ? ORDER BY id LIMIT ?",
            [run_id, int(after), int(limit)],
        )
        return [decode(r) for r in rows]

    def last_events(self, run_id, limit=200):
        """Latest events, without ``collect.progress`` ticks that would crowd out the rest
        (they only reach clients through the change stream and :meth:`last_event`)."""
        rows = self.db.execute(
            "SELECT * FROM (SELECT * FROM run_events WHERE run_id = ? AND "
            "event_type != 'collect.progress' ORDER BY id DESC LIMIT ?) ORDER BY id",
            [run_id, int(limit)],
        )
        return [decode(r) for r in rows]

    def last_event(self, run_id, event_type):
        """Most recent event of one type, or ``None``."""
        row = self.db.execute(
            "SELECT * FROM run_events WHERE run_id = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
            [run_id, event_type],
        ).fetchone()
        return decode(row) if row else None

    def milestones(self, run_id, limit=500):
        """Latest non-routine events (launch phases, batches, failures): never crowded out
        by thousands of routine ``study.state``/``preflight.check`` lines."""
        rows = self.db.execute(
            "SELECT * FROM (SELECT * FROM run_events WHERE run_id = ? AND NOT "
            "(event_type IN ('study.state', 'preflight.check', 'collect.progress') AND level = 'info') "
            "ORDER BY id DESC LIMIT ?) ORDER BY id",
            [run_id, int(limit)],
        )
        return [decode(r) for r in rows]

    # Studies ---------------------------------------------------------------------------
    def upsert_study(self, run_id, name, **fields):
        points = fields.pop("points", None)
        with self._write() as db:
            if not db.execute("SELECT 1 FROM runs WHERE id = ?", [run_id]).fetchone():
                return
            row = decode(
                db.execute(
                    "SELECT * FROM studies WHERE run_id = ? AND name = ?", [run_id, name]
                ).fetchone()
            )
            merged = {**(row or {}), **fields}
            if points:
                fields["series_json"] = merge_series((row or {}).get("series_json"), points)
            if merged.get("state") == "completed":
                fields["progress"] = 1.0
            elif merged.get("sim_time_s") is not None and merged.get("final_time_s"):
                fields["progress"] = min(1.0, merged["sim_time_s"] / merged["final_time_s"])
            rev = self._bump(db)
            values = encode({**fields, "updated_at": time.time(), "rev": rev})
            if row is None:
                values.update(run_id=run_id, name=name)
                db.execute(
                    f"INSERT INTO studies ({', '.join(values)}) "
                    f"VALUES ({', '.join('?' * len(values))})",
                    list(values.values()),
                )
            else:
                assignments = ", ".join(f"{k} = ?" for k in values)
                db.execute(
                    f"UPDATE studies SET {assignments} WHERE run_id = ? AND name = ?",
                    [*values.values(), run_id, name],
                )
            if "state" in fields:
                self._refresh_counts(db, run_id, rev)

    def _refresh_counts(self, db, run_id, rev):
        counts = {
            r["state"]: r["n"]
            for r in db.execute(
                "SELECT state, COUNT(*) AS n FROM studies WHERE run_id = ? GROUP BY state",
                [run_id],
            )
        }
        preview = db.execute("SELECT preview_json FROM runs WHERE id = ?", [run_id]).fetchone()
        expected = (json.loads(preview[0]) if preview and preview[0] else {}).get("study_count")
        total = sum(counts.values())
        if expected and expected > total:
            counts["pending"] = counts.get("pending", 0) + expected - total
            total = expected
        done = sum(counts.get(s, 0) for s in FINISHED_STUDIES)
        db.execute(
            "UPDATE runs SET counts_json = ?, progress = ?, rev = ?, updated_at = ? WHERE id = ?",
            [
                json.dumps(counts, sort_keys=True),
                done / total if total else None,
                rev,
                time.time(),
                run_id,
            ],
        )

    def studies(self, run_id):
        rows = self.db.execute("SELECT * FROM studies WHERE run_id = ? ORDER BY name", [run_id])
        return [decode(r) for r in rows]

    # Streaming and summaries -------------------------------------------------------------
    def changes(self, rev, event_id, limit=2000):
        db = self.db
        db.execute("BEGIN")
        try:
            current = db.execute("SELECT value FROM meta WHERE key = 'rev'").fetchone()[0]
            last_event = db.execute("SELECT COALESCE(MAX(id), 0) FROM run_events").fetchone()[0]
            deleted = db.execute("SELECT id FROM deleted_runs WHERE rev > ?", [rev]).fetchall()
            hosts = db.execute("SELECT * FROM hosts WHERE rev > ?", [rev]).fetchall()
            runs = db.execute(
                "SELECT * FROM runs WHERE rev > ? ORDER BY rev LIMIT ?", [rev, limit]
            ).fetchall()
            studies = db.execute(
                "SELECT * FROM studies WHERE rev > ? ORDER BY rev LIMIT ?", [rev, limit]
            ).fetchall()
            events = db.execute(
                "SELECT * FROM run_events WHERE id > ? ORDER BY id LIMIT ?", [event_id, limit]
            ).fetchall()
        finally:
            db.execute("COMMIT")
        events = [decode(r) for r in events]
        return {
            "rev": current,
            "deleted_runs": [r["id"] for r in deleted],
            "event_id": events[-1]["id"] if len(events) == limit else last_event,
            "hosts": [decode(r) for r in hosts],
            "runs": [decode(r) for r in runs],
            "studies": [decode(r) for r in studies],
            "events": events,
        }

    def kpis(self):
        db = self.db
        week = time.time() - 7 * 86400
        placeholders = ", ".join("?" * len(ACTIVE))
        active = db.execute(
            f"SELECT COUNT(*) FROM runs WHERE status IN ({placeholders})", ACTIVE
        ).fetchone()[0]
        running = db.execute(
            "SELECT COUNT(*) FROM studies JOIN runs ON runs.id = studies.run_id "
            f"WHERE studies.state = 'running' AND runs.status IN ({placeholders})",
            ACTIVE,
        ).fetchone()[0]
        completed = db.execute(
            "SELECT COUNT(*) FROM runs WHERE status = 'completed' AND finished_at > ?", [week]
        ).fetchone()[0]
        failed = db.execute(
            "SELECT COUNT(*) FROM runs WHERE status IN ('failed', 'lost') AND "
            "COALESCE(finished_at, updated_at) > ?",
            [week],
        ).fetchone()[0]
        return {
            "active": active,
            "running_studies": running,
            "completed_7d": completed,
            "failed_7d": failed,
            "total": db.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
        }
