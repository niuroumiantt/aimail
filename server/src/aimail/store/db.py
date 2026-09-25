"""连接与建表。一个文件、WAL、外键开。schema.sql 是幂等的,每次连接都跑一遍。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


def _migrate_reply_attempt(conn: sqlite3.Connection) -> None:
    """Extend the attempt state constraint without discarding uncertain-send evidence."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='reply_attempt'"
    ).fetchone()
    if not row or "resolved_not_sent" in row["sql"]:
        return
    conn.execute("BEGIN EXCLUSIVE")
    try:
        # Another app process may have completed this one-time migration while we waited.
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='reply_attempt'"
        ).fetchone()
        if not row or "resolved_not_sent" in row["sql"]:
            conn.commit()
            return
        conn.execute("DROP INDEX IF EXISTS reply_unresolved")
        conn.execute("ALTER TABLE reply_attempt RENAME TO reply_attempt_legacy")
        conn.execute(
            "CREATE TABLE reply_attempt ("
            "id INTEGER PRIMARY KEY, thread_id INTEGER NOT NULL REFERENCES thread(id), "
            "token_hash TEXT NOT NULL UNIQUE, sender TEXT NOT NULL, actor TEXT NOT NULL, "
            "raw BLOB NOT NULL, state TEXT NOT NULL CHECK(state IN "
            "('sending','unknown','recorded','resolved_not_sent')), created_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO reply_attempt(id,thread_id,token_hash,sender,actor,raw,state,created_at) "
            "SELECT id,thread_id,token_hash,sender,actor,raw,state,created_at "
            "FROM reply_attempt_legacy"
        )
        conn.execute("DROP TABLE reply_attempt_legacy")
        conn.execute(
            "CREATE UNIQUE INDEX reply_unresolved ON reply_attempt(thread_id) "
            "WHERE state IN ('sending','unknown')"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    _migrate_reply_attempt(conn)
    conn.executescript(SCHEMA.read_text("utf-8"))
    return conn
