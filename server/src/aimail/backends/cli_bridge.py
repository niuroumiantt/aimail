"""Opt-in SSH-pulled CLI task queue, separate from every mailbox connection.

Only the existing trusted SSH operator accesses heartbeat/claim/finish. No HTTP
endpoint, provider credential or access to the original mailbox database is added.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

BACKENDS = {"codex_cli": "CODEX_CLI_MODEL", "claude_code_cli": "CLAUDE_CODE_CLI_MODEL"}
WORKER_TTL = 120
RETENTION = 3600


class BridgeError(RuntimeError):
    """A safe error code; never contains task text, process output or credentials."""


def enabled() -> bool:
    return os.environ.get("LLM_CLI_BRIDGE_ENABLED", "") == "1"


def _limits() -> tuple[float, int, int]:
    try:
        timeout = float(os.environ.get("LLM_CLI_TIMEOUT", "180"))
        source_limit = int(os.environ.get("LLM_CLI_BRIDGE_MAX_INPUT_BYTES", "1048576"))
        output_limit = int(os.environ.get("LLM_CLI_MAX_OUTPUT_BYTES", "2097152"))
    except ValueError:
        raise BridgeError("invalid_configuration") from None
    if not math.isfinite(timeout) or not 0.05 <= timeout <= 3600:
        raise BridgeError("invalid_configuration")
    if not 1024 <= source_limit <= 16777216 or not 1024 <= output_limit <= 16777216:
        raise BridgeError("invalid_configuration")
    return timeout, source_limit, output_limit


def database_path() -> Path:
    configured_mailbox = os.environ.get("DB_PATH", "").strip()
    legacy = Path("data/mail2leads.sqlite3")
    mailbox_path = (
        Path(configured_mailbox)
        if configured_mailbox
        else (legacy if legacy.exists() else Path("data/aimail.sqlite3"))
    )
    configured = os.environ.get("LLM_CLI_BRIDGE_DB", "").strip()
    path = Path(configured) if configured else mailbox_path.parent / "cli-bridge.sqlite3"
    same_file = path.exists() and mailbox_path.exists() and path.samefile(mailbox_path)
    if same_file or path.resolve() == mailbox_path.resolve():
        raise BridgeError("invalid_configuration")
    return path


@contextmanager
def _database():
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(descriptor)
    os.chmod(path, 0o600)
    connection = sqlite3.connect(path, timeout=2, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=2000")
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS worker (
                backend TEXT PRIMARY KEY, worker_id TEXT NOT NULL, model TEXT NOT NULL,
                expires_at REAL NOT NULL, heartbeat_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS job (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nonce TEXT NOT NULL UNIQUE,
                backend TEXT NOT NULL, model TEXT NOT NULL,
                system TEXT NOT NULL, user TEXT NOT NULL, schema_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('queued','running','ok','failed')),
                created_at REAL NOT NULL, deadline REAL NOT NULL,
                worker_id TEXT, lease_token TEXT, lease_expires_at REAL,
                output TEXT, output_hash TEXT, reason TEXT, finished_at REAL
            );
            CREATE INDEX IF NOT EXISTS pending_job ON job(status, created_at);
        """)
        yield connection
    except sqlite3.Error:
        raise BridgeError("queue_unavailable") from None
    finally:
        connection.close()


def _expire(connection, now: float) -> None:
    connection.execute(
        "UPDATE job SET status='failed', reason='request_timeout', finished_at=? "
        "WHERE status IN ('queued','running') AND deadline<=?",
        (now, now),
    )
    connection.execute(
        "UPDATE job SET status='failed', reason='worker_disconnected', finished_at=? "
        "WHERE status='running' AND lease_expires_at<=?",
        (now, now),
    )
    connection.execute("DELETE FROM job WHERE finished_at<?", (now - RETENTION,))
    connection.execute("DELETE FROM worker WHERE heartbeat_at<?", (now - 7 * 86400,))


def _identifier(value) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        raise BridgeError("invalid_request")
    if not all(char.isascii() and (char.isalnum() or char in "_-.") for char in value):
        raise BridgeError("invalid_request")
    return value


def _model(value) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 200
        or value.startswith("-")
        or any(ord(char) < 32 for char in value)
        or "://" in value
        or any(char in "@?#" for char in value)
    ):
        raise BridgeError("invalid_request")
    return value


def model_name(backend: str) -> str:
    configured = os.environ.get(BACKENDS[backend], "").strip()
    if configured:
        return configured
    if not enabled():
        return ""
    try:
        with _database() as connection:
            row = connection.execute(
                "SELECT model FROM worker WHERE backend=?", (backend,)
            ).fetchone()
    except (BridgeError, OSError):
        return ""
    return row["model"] if row else ""


def ready(backend: str, model: str | None = None) -> tuple[bool, str]:
    if not enabled():
        return False, "CLI 工作站桥接未启用"
    try:
        _limits()
        selected = _model(model if model is not None else model_name(backend))
        with _database() as connection:
            row = connection.execute(
                "SELECT model FROM worker WHERE backend=? AND expires_at>?", (backend, time.time())
            ).fetchone()
        if row and row["model"] == selected:
            return True, "已连接经过合成任务验收的 CLI 工作站"
    except (BridgeError, OSError):
        return False, "CLI 工作站配置未完成"
    return False, "CLI 工作站未连接或型号未就绪"


def heartbeat(worker_id: str, capabilities: list[dict], lease_seconds: int = WORKER_TTL) -> dict:
    if not enabled():
        raise BridgeError("bridge_disabled")
    worker_id = _identifier(worker_id)
    if not isinstance(capabilities, list) or not 1 <= len(capabilities) <= 2:
        raise BridgeError("invalid_request")
    if not isinstance(lease_seconds, int) or not 30 <= lease_seconds <= WORKER_TTL:
        raise BridgeError("invalid_request")
    seen = set()
    for item in capabilities:
        if not isinstance(item, dict) or item.get("backend") not in BACKENDS:
            raise BridgeError("invalid_request")
        if item.get("verified") is not True or item["backend"] in seen:
            raise BridgeError("invalid_request")
        seen.add(item["backend"])
        _model(item.get("model"))
        configured = os.environ.get(BACKENDS[item["backend"]], "").strip()
        if configured and configured != item["model"]:
            raise BridgeError("model_mismatch")
    with _database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        now = time.time()
        _expire(connection, now)
        for item in capabilities:
            old = connection.execute(
                "SELECT * FROM worker WHERE backend=?", (item["backend"],)
            ).fetchone()
            if old and old["expires_at"] > now and old["worker_id"] != worker_id:
                raise BridgeError("worker_conflict")
            active = connection.execute(
                "SELECT 1 FROM job WHERE backend=? AND status='running' LIMIT 1", (item["backend"],)
            ).fetchone()
            if old and old["model"] != item["model"] and active:
                raise BridgeError("worker_conflict")
            connection.execute(
                "INSERT INTO worker VALUES(?,?,?,?,?) ON CONFLICT(backend) DO UPDATE SET "
                "worker_id=excluded.worker_id,model=excluded.model,"
                "expires_at=excluded.expires_at,heartbeat_at=excluded.heartbeat_at",
                (item["backend"], worker_id, item["model"], now + lease_seconds, now),
            )
        connection.execute(
            "UPDATE job SET lease_expires_at=MIN(deadline,?) "
            "WHERE worker_id=? AND status='running'",
            (now + lease_seconds, worker_id),
        )
        connection.commit()
    return {"ok": True}


def submit(backend: str, model: str, system: str, user: str, schema: dict) -> tuple[int, str]:
    if not enabled():
        raise BridgeError("bridge_disabled")
    timeout, input_limit, _ = _limits()
    if backend not in BACKENDS or not isinstance(system, str) or not isinstance(user, str):
        raise BridgeError("invalid_request")
    _model(model)
    if not isinstance(schema, dict):
        raise BridgeError("invalid_request")
    content = json.dumps({"system": system, "user": user, "schema": schema}, ensure_ascii=False)
    if len(content.encode()) > input_limit:
        raise BridgeError("input_too_large")
    nonce = secrets.token_hex(24)
    with _database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        now = time.time()
        _expire(connection, now)
        worker = connection.execute(
            "SELECT * FROM worker WHERE backend=? AND model=? AND expires_at>?",
            (backend, model, now),
        ).fetchone()
        if not worker:
            raise BridgeError("worker_disconnected")
        count = connection.execute(
            "SELECT COUNT(*) FROM job WHERE status IN ('queued','running')"
        ).fetchone()[0]
        if count >= 32:
            raise BridgeError("queue_busy")
        cursor = connection.execute(
            "INSERT INTO job(nonce,backend,model,system,user,schema_json,"
            "status,created_at,deadline) "
            "VALUES(?,?,?,?,?,?,'queued',?,?)",
            (
                nonce,
                backend,
                model,
                system,
                user,
                json.dumps(schema, ensure_ascii=False),
                now,
                now + timeout,
            ),
        )
        connection.commit()
    return cursor.lastrowid, nonce


def claim(worker_id: str) -> dict:
    if not enabled():
        raise BridgeError("bridge_disabled")
    worker_id = _identifier(worker_id)
    with _database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        now = time.time()
        _expire(connection, now)
        if connection.execute(
            "SELECT 1 FROM job WHERE worker_id=? AND status='running' LIMIT 1", (worker_id,)
        ).fetchone():
            connection.commit()
            return {"job": None}
        row = connection.execute(
            "SELECT j.*,w.expires_at FROM job j JOIN worker w ON j.backend=w.backend "
            "AND j.model=w.model WHERE j.status='queued' AND w.worker_id=? "
            "AND w.expires_at>? ORDER BY j.created_at,j.id LIMIT 1",
            (worker_id, now),
        ).fetchone()
        if row is None:
            connection.commit()
            return {"job": None}
        lease = secrets.token_hex(24)
        connection.execute(
            "UPDATE job SET status='running',worker_id=?,lease_token=?,lease_expires_at=? "
            "WHERE id=? AND status='queued'",
            (worker_id, lease, min(row["deadline"], row["expires_at"]), row["id"]),
        )
        connection.commit()
    return {
        "job": {
            "id": row["id"],
            "nonce": row["nonce"],
            "lease_token": lease,
            "backend": row["backend"],
            "model": row["model"],
            "system": row["system"],
            "user": row["user"],
            "schema": json.loads(row["schema_json"]),
        }
    }


def finish(
    worker_id: str,
    job_id: int,
    nonce: str,
    lease_token: str,
    output: str | None = None,
    error: str | None = None,
) -> dict:
    if not enabled():
        raise BridgeError("bridge_disabled")
    worker_id, nonce, lease_token = map(_identifier, (worker_id, nonce, lease_token))
    if not isinstance(job_id, int) or isinstance(job_id, bool) or job_id < 1:
        raise BridgeError("invalid_request")
    _, _, output_limit = _limits()
    failure = error is not None
    if not failure and (not isinstance(output, str) or len(output.encode()) > output_limit):
        raise BridgeError("output_too_large")
    output_hash = hashlib.sha256(output.encode()).hexdigest() if not failure else None
    with _database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        now = time.time()
        _expire(connection, now)
        row = connection.execute("SELECT * FROM job WHERE id=?", (job_id,)).fetchone()
        matches = (
            row
            and row["nonce"] == nonce
            and row["worker_id"] == worker_id
            and row["lease_token"] == lease_token
        )
        if not matches:
            connection.commit()
            return {"accepted": False}
        if row["status"] == "ok":
            connection.commit()
            return {"accepted": not failure and row["output_hash"] == output_hash}
        if row["status"] != "running":
            connection.commit()
            return {"accepted": False}
        # An error supplied by a CLI may contain private content. Persist a fixed code.
        connection.execute(
            "UPDATE job SET status=?,output=?,output_hash=?,reason=?,finished_at=? WHERE id=?",
            (
                "failed" if failure else "ok",
                None if failure else output,
                output_hash,
                "worker_call_failed" if failure else None,
                now,
                job_id,
            ),
        )
        connection.commit()
    return {"accepted": True}


def result(job_id: int, nonce: str) -> tuple[str, str | None]:
    with _database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        _expire(connection, time.time())
        row = connection.execute(
            "SELECT * FROM job WHERE id=? AND nonce=?", (job_id, nonce)
        ).fetchone()
        connection.commit()
    if row is None:
        raise BridgeError("job_expired")
    return row["status"], row["output"] if row["status"] == "ok" else row["reason"]


def discard(job_id: int, nonce: str) -> None:
    with _database() as connection:
        connection.execute("DELETE FROM job WHERE id=? AND nonce=?", (job_id, nonce))


def complete(backend: str, system: str, user: str, schema: dict, model: str | None = None) -> str:
    selected = model if model is not None else model_name(backend)
    job_id, nonce = submit(backend, selected, system, user, schema)
    try:
        while True:
            status, value = result(job_id, nonce)
            if status == "ok":
                return value
            if status == "failed":
                raise BridgeError(value or "worker_call_failed")
            time.sleep(0.1)
    finally:
        # The main application stores its validated output; do not retain duplicate
        # private mail text here. A late remote finish now has nothing to overwrite.
        discard(job_id, nonce)
