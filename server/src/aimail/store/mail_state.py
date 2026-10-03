"""可恢复的会话整理。保留原文、线索、跟进与同步游标，不操作远端邮箱。"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime


def deleted_at(conn: sqlite3.Connection, thread_id: int) -> str:
    row = conn.execute(
        "SELECT deleted_at FROM thread_mail_state WHERE thread_id=?", (thread_id,)
    ).fetchone()
    return str(row[0]) if row else ""


def change(conn: sqlite3.Connection, thread_id: int, action: str, actor: str) -> None:
    if action not in {"trash", "restore", "new_message"} or not actor.strip():
        raise ValueError("需要有效的操作和操作人")
    own_transaction = not conn.in_transaction
    if own_transaction:
        conn.execute("BEGIN IMMEDIATE")
    try:
        target_deleted = action == "trash"
        if bool(deleted_at(conn, thread_id)) != target_deleted:
            at = datetime.now(UTC).isoformat()
            conn.execute(
                "INSERT INTO thread_mail_state(thread_id,deleted_at,deleted_by) VALUES(?,?,?) "
                "ON CONFLICT(thread_id) DO UPDATE SET "
                "deleted_at=excluded.deleted_at,deleted_by=excluded.deleted_by",
                (thread_id, at if target_deleted else "", actor if target_deleted else ""),
            )
            conn.execute(
                "INSERT INTO thread_mail_event(thread_id,action,actor,at) VALUES(?,?,?,?)",
                (thread_id, action, actor, at),
            )
        if own_transaction:
            conn.commit()
    except Exception:
        if own_transaction:
            conn.rollback()
        raise
