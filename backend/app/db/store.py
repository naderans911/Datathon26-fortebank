"""Small durable SQLite queue; every claim and admission is transactional."""

import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class CapacityError(Exception):
    pass


class RateLimitError(Exception):
    pass


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, owner TEXT, is_demo INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL, stage TEXT NOT NULL, filename TEXT NOT NULL,
                    source_path TEXT NOT NULL, size_bytes INTEGER NOT NULL DEFAULT 0,
                    disk_bytes INTEGER NOT NULL DEFAULT 0,
                    reserved_bytes INTEGER NOT NULL DEFAULT 0, checksum TEXT,
                    accepted_at REAL NOT NULL, updated_at REAL NOT NULL, deadline_at REAL NOT NULL,
                    claimed_by TEXT, detector_version TEXT, rules_snapshot TEXT NOT NULL,
                    result TEXT, error TEXT
                );
                CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status, accepted_at);
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workers (
                    id TEXT PRIMARY KEY, heartbeat_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rate_events (
                    subject TEXT NOT NULL, occurred_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS rate_subject ON rate_events(subject, occurred_at);
            """)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)")}
            if "disk_bytes" not in columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN disk_bytes INTEGER NOT NULL DEFAULT 0")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=15000")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def decode(row):
        if row is None:
            return None
        job = dict(row)
        for field in ("rules_snapshot", "result", "error"):
            job[field] = json.loads(job[field]) if job[field] else None
        return job

    def session(self, cookie: str | None):
        if not cookie:
            return None
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE id=? AND expires_at>?", (token_hash(cookie), time.time())
            ).fetchone()
        return dict(row) if row else None

    def new_session(self, hours: int):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.connect() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at<?", (time.time(),))
            connection.execute("INSERT INTO sessions VALUES (?,?,?)", (
                token_hash(token), csrf, time.time() + hours * 3600,
            ))
        return token, csrf

    def reserve(self, job: dict, settings, subjects: list[str], used_bytes: int):
        now = time.time()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            count = connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN ('receiving','queued','processing') AND is_demo=0"
            ).fetchone()[0]
            if count >= settings.max_queue_size:
                raise CapacityError("The analysis queue is full. Try again after a job finishes.")
            reserved = connection.execute("SELECT COALESCE(SUM(reserved_bytes),0) FROM jobs").fetchone()[0]
            persisted_sources = connection.execute("SELECT COALESCE(SUM(MAX(size_bytes,disk_bytes)),0) FROM jobs").fetchone()[0]
            allocation = settings.max_upload_bytes + settings.max_job_output_mb * 1024 * 1024
            if max(used_bytes, persisted_sources) + reserved + allocation > settings.max_storage_mb * 1024 * 1024:
                raise CapacityError("Storage capacity is unavailable. Remove retained jobs or contact the operator.")
            connection.execute("DELETE FROM rate_events WHERE occurred_at<?", (now - 3600,))
            for subject in subjects:
                attempts = connection.execute(
                    "SELECT COUNT(*) FROM rate_events WHERE subject=? AND occurred_at>?", (subject, now - 3600)
                ).fetchone()[0]
                if attempts >= settings.upload_rate_per_hour:
                    raise RateLimitError("Upload rate limit reached. Try again later.")
            for subject in subjects:
                connection.execute("INSERT INTO rate_events VALUES (?,?)", (subject, now))
            connection.execute("""
                INSERT INTO jobs (id,owner,is_demo,status,stage,filename,source_path,reserved_bytes,
                  accepted_at,updated_at,deadline_at,detector_version,rules_snapshot)
                VALUES (?,?,0,'receiving','validating_video',?,?,?,?,?,?,?,?)
            """, (job["id"], job.get("owner"), job["filename"], job["source_path"], allocation,
                  now, now, now + settings.job_deadline_seconds, job.get("detector_version"),
                  json.dumps(job["rules_snapshot"], ensure_ascii=False)))

    def accept(self, job_id: str, size: int, checksum: str, deadline_seconds: float, output_bytes: int = 0):
        now = time.time()
        with self.connect() as connection:
            connection.execute("""UPDATE jobs SET status='queued',size_bytes=?,reserved_bytes=?,checksum=?,
                accepted_at=?,updated_at=?,deadline_at=? WHERE id=? AND status='receiving'""",
                (size, output_bytes, checksum, now, now, now + deadline_seconds, job_id))

    def get(self, job_id: str):
        with self.connect() as connection:
            return self.decode(connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def heartbeat(self, worker_id: str):
        with self.connect() as connection:
            connection.execute("INSERT INTO workers VALUES (?,?) ON CONFLICT(id) DO UPDATE SET heartbeat_at=excluded.heartbeat_at",
                               (worker_id, time.time()))

    def last_heartbeat(self):
        with self.connect() as connection:
            return connection.execute("SELECT MAX(heartbeat_at) FROM workers").fetchone()[0]

    def remove_worker(self, worker_id: str):
        with self.connect() as connection:
            connection.execute("DELETE FROM workers WHERE id=?", (worker_id,))

    def recover(self, stale_seconds: float):
        now = time.time()
        timeout = json.dumps({"code": "deadline_exceeded", "message": "The analysis deadline expired. No complete verdict was produced."})
        interrupted = json.dumps({"code": "worker_interrupted", "message": "The analysis worker stopped before completion. Submit a new job to retry."})
        with self.connect() as connection:
            connection.execute("UPDATE jobs SET status='failed',stage='Failed',error=?,updated_at=?,reserved_bytes=0 WHERE status IN ('queued','processing') AND deadline_at<=?",
                               (timeout, now, now))
            connection.execute("UPDATE jobs SET status='failed',stage='Failed',error=?,updated_at=?,reserved_bytes=0 WHERE status='processing' AND updated_at<?",
                               (interrupted, now, now - stale_seconds))
            # Interrupted uploads have no accepted client job; remove their reservations.
            connection.execute("UPDATE jobs SET status='failed',stage='Failed',error=?,updated_at=?,reserved_bytes=0 WHERE status='receiving' AND updated_at<?",
                               (interrupted, now, now - max(600, stale_seconds)))

    def claim(self, worker_id: str, capacity: int = 1):
        now = time.time()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            running = connection.execute("SELECT COUNT(*) FROM jobs WHERE status='processing' AND is_demo=0").fetchone()[0]
            if running >= capacity:
                return None
            row = connection.execute("SELECT id FROM jobs WHERE status='queued' AND is_demo=0 AND deadline_at>? ORDER BY accepted_at LIMIT 1", (now,)).fetchone()
            if not row:
                return None
            connection.execute("UPDATE jobs SET status='processing',claimed_by=?,updated_at=? WHERE id=? AND status='queued'", (worker_id, now, row["id"]))
            return self.decode(connection.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())

    def progress(self, job_id: str, stage: str | None = None):
        with self.connect() as connection:
            if stage is None:
                connection.execute("UPDATE jobs SET updated_at=? WHERE id=? AND status='processing'", (time.time(), job_id))
            else:
                connection.execute("UPDATE jobs SET stage=?,updated_at=? WHERE id=? AND status='processing'", (stage, time.time(), job_id))

    def detector_used(self, job_id: str, version: str):
        with self.connect() as connection:
            connection.execute("UPDATE jobs SET detector_version=? WHERE id=? AND status='processing'", (version, job_id))

    def complete(self, job_id: str, result: dict) -> bool:
        now = time.time()
        with self.connect() as connection:
            row = connection.execute("SELECT source_path FROM jobs WHERE id=?", (job_id,)).fetchone()
            disk_bytes = self.directory_bytes(Path(row["source_path"]).parent) if row else 0
            cursor = connection.execute("UPDATE jobs SET status='done',stage='complete',result=?,updated_at=?,reserved_bytes=0,disk_bytes=? WHERE id=? AND status='processing' AND deadline_at>?", (json.dumps(result, ensure_ascii=False), now, disk_bytes, job_id, now))
            return cursor.rowcount == 1

    def fail(self, job_id: str, code: str, message: str):
        with self.connect() as connection:
            row = connection.execute("SELECT source_path FROM jobs WHERE id=?", (job_id,)).fetchone()
            disk_bytes = self.directory_bytes(Path(row["source_path"]).parent) if row else 0
            connection.execute("UPDATE jobs SET status='failed',stage='Failed',error=?,updated_at=?,reserved_bytes=0,disk_bytes=? WHERE id=? AND status NOT IN ('done','failed')", (json.dumps({"code": code, "message": message}), time.time(), disk_bytes, job_id))

    def delete(self, job_id: str):
        with self.connect() as connection:
            connection.execute("DELETE FROM jobs WHERE id=?", (job_id,))

    def expired(self, hours: float):
        with self.connect() as connection:
            return [self.decode(row) for row in connection.execute("SELECT * FROM jobs WHERE status IN ('done','failed') AND accepted_at<?", (time.time() - hours * 3600,)).fetchall()]

    def add_demo(self, payload: dict, owner: str, source_dir: Path):
        now = time.time()
        with self.connect() as connection:
            connection.execute("""INSERT INTO jobs (id,owner,is_demo,status,stage,filename,source_path,size_bytes,disk_bytes,
                accepted_at,updated_at,deadline_at,detector_version,rules_snapshot,result,error)
                VALUES (?,?,1,?,?,?,?,?,?,?,?,?,'synthetic-demo','[]',?,?)""", (
                    payload["job_id"], owner, payload["status"], payload.get("stage", "Complete"),
                    payload.get("filename", "Synthetic demonstration.mov"), str(source_dir / "source.mov"),
                    payload.get("size_bytes", 0), self.directory_bytes(source_dir), payload.get("created_at", now), payload.get("updated_at", now),
                    now, json.dumps(payload.get("result")), json.dumps(payload.get("error")),
                ))

    @staticmethod
    def directory_bytes(directory: Path) -> int:
        total = 0
        for path in directory.rglob("*"):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except FileNotFoundError:
                pass
        return total
