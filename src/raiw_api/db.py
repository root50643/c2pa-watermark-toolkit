from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Small SQLite repository with one connection per operation."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS customers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    external_id TEXT,
                    contact TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                    prefix TEXT NOT NULL UNIQUE,
                    key_hmac TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    revoked_at TEXT,
                    last_used_at TEXT
                );

                CREATE TABLE IF NOT EXISTS archive_requests (
                    request_id TEXT PRIMARY KEY,
                    customer_id TEXT REFERENCES customers(id),
                    key_id TEXT REFERENCES api_keys(id),
                    received_at TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    params_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_code TEXT,
                    error_message TEXT,
                    input_path TEXT NOT NULL,
                    input_sha256 TEXT NOT NULL,
                    input_size INTEGER NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    mime TEXT NOT NULL,
                    output_path TEXT,
                    output_sha256 TEXT,
                    output_size INTEGER,
                    response_path TEXT,
                    manifest_path TEXT NOT NULL,
                    app_version TEXT NOT NULL,
                    upstream_version TEXT NOT NULL,
                    git_commit TEXT NOT NULL,
                    duration_ms REAL,
                    job_id TEXT
                );

                CREATE TABLE IF NOT EXISTS access_logs (
                    request_id TEXT PRIMARY KEY,
                    customer_id TEXT REFERENCES customers(id),
                    key_id TEXT REFERENCES api_keys(id),
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    client_ip TEXT NOT NULL,
                    peer_ip TEXT NOT NULL,
                    user_agent TEXT NOT NULL,
                    method TEXT NOT NULL,
                    route TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    duration_ms REAL NOT NULL,
                    request_bytes INTEGER,
                    response_bytes INTEGER,
                    archive_id TEXT REFERENCES archive_requests(request_id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    archive_id TEXT NOT NULL UNIQUE REFERENCES archive_requests(request_id),
                    task_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    message TEXT,
                    result_path TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_access_customer_time ON access_logs(customer_id, started_at);
                CREATE INDEX IF NOT EXISTS idx_access_ip_time ON access_logs(client_ip, started_at);
                CREATE INDEX IF NOT EXISTS idx_archive_received ON archive_requests(received_at);
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(1, ?)",
                (utc_now(),),
            )

    def _one(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
        return dict(row) if row else None

    def _all(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def create_customer(
        self, name: str, external_id: str | None = None, contact: str | None = None
    ) -> dict[str, Any]:
        customer_id = str(uuid.uuid4())
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO customers(id,name,external_id,contact,active,created_at,updated_at) VALUES(?,?,?,?,1,?,?)",
                (customer_id, name, external_id, contact, now, now),
            )
        return self.get_customer(customer_id) or {}

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM customers WHERE id=?", (customer_id,))

    def list_customers(self) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM customers ORDER BY created_at")

    def set_customer_active(self, customer_id: str, active: bool) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "UPDATE customers SET active=?,updated_at=? WHERE id=?",
                (int(active), utc_now(), customer_id),
            )
        return cur.rowcount == 1

    def insert_api_key(self, customer_id: str, prefix: str, key_hmac: str) -> dict[str, Any]:
        key_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO api_keys(id,customer_id,prefix,key_hmac,created_at) VALUES(?,?,?,?,?)",
                (key_id, customer_id, prefix, key_hmac, utc_now()),
            )
        return self.get_api_key(key_id) or {}

    def get_api_key(self, key_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM api_keys WHERE id=?", (key_id,))

    def find_api_key_by_prefix(self, prefix: str) -> dict[str, Any] | None:
        return self._one(
            """SELECT k.*,c.name AS customer_name,c.external_id,c.active AS customer_active
               FROM api_keys k JOIN customers c ON c.id=k.customer_id WHERE k.prefix=?""",
            (prefix,),
        )

    def list_api_keys(self, customer_id: str | None = None) -> list[dict[str, Any]]:
        if customer_id:
            return self._all(
                "SELECT id,customer_id,prefix,created_at,revoked_at,last_used_at FROM api_keys WHERE customer_id=?",
                (customer_id,),
            )
        return self._all("SELECT id,customer_id,prefix,created_at,revoked_at,last_used_at FROM api_keys")

    def touch_api_key(self, key_id: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE api_keys SET last_used_at=? WHERE id=?", (utc_now(), key_id))

    def revoke_api_key(self, key_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "UPDATE api_keys SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
                (utc_now(), key_id),
            )
        return cur.rowcount == 1

    def insert_archive(self, row: dict[str, Any]) -> None:
        columns = ",".join(row)
        placeholders = ",".join("?" for _ in row)
        with self.connect() as conn:
            conn.execute(f"INSERT INTO archive_requests({columns}) VALUES({placeholders})", tuple(row.values()))

    def update_archive(self, request_id: str, **changes: Any) -> None:
        if not changes:
            return
        assignments = ",".join(f"{column}=?" for column in changes)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE archive_requests SET {assignments} WHERE request_id=?",  # noqa: S608
                (*changes.values(), request_id),
            )

    def get_archive(self, request_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM archive_requests WHERE request_id=?", (request_id,))

    def list_archives(self) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM archive_requests ORDER BY received_at")

    def delete_archive_record(self, request_id: str) -> bool:
        with self.connect() as conn:
            conn.execute("DELETE FROM jobs WHERE archive_id=?", (request_id,))
            cur = conn.execute("DELETE FROM archive_requests WHERE request_id=?", (request_id,))
        return cur.rowcount == 1

    def insert_access_log(self, row: dict[str, Any]) -> None:
        columns = ",".join(row)
        placeholders = ",".join("?" for _ in row)
        with self.connect() as conn:
            conn.execute(f"INSERT OR REPLACE INTO access_logs({columns}) VALUES({placeholders})", tuple(row.values()))

    def list_access_logs(
        self,
        *,
        customer_id: str | None = None,
        client_ip: str | None = None,
        route: str | None = None,
        start: str | None = None,
        end: str | None = None,
        status: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, value, operator in (
            ("customer_id", customer_id, "="),
            ("client_ip", client_ip, "="),
            ("route", route, "="),
            ("started_at", start, ">="),
            ("started_at", end, "<="),
            ("status_code", status, "="),
        ):
            if value is not None:
                clauses.append(f"{column}{operator}?")
                params.append(value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return self._all(f"SELECT * FROM access_logs{where} ORDER BY started_at", tuple(params))  # noqa: S608

    def create_job(self, archive_id: str, task_name: str) -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO jobs(id,archive_id,task_name,status,progress,created_at,updated_at)
                   VALUES(?,?,?,'queued',0,?,?)""",
                (job_id, archive_id, task_name, now, now),
            )
            conn.execute(
                "UPDATE archive_requests SET job_id=?,status='queued' WHERE request_id=?",
                (job_id, archive_id),
            )
        return self.get_job(job_id) or {}

    def update_job(self, job_id: str, **changes: Any) -> None:
        changes["updated_at"] = utc_now()
        assignments = ",".join(f"{column}=?" for column in changes)
        with self.connect() as conn:
            conn.execute(f"UPDATE jobs SET {assignments} WHERE id=?", (*changes.values(), job_id))  # noqa: S608

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM jobs WHERE id=?", (job_id,))

    @staticmethod
    def decode_params(row: dict[str, Any]) -> dict[str, Any]:
        return json.loads(row.get("params_json") or "{}")
