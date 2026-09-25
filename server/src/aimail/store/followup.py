"""Durable, versioned responsibility transfers; no mailbox-wide grants."""

import json
import sqlite3
from datetime import UTC, datetime


def init(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS followup (
      thread_id INTEGER PRIMARY KEY REFERENCES thread(id),
      owner TEXT NOT NULL,
      pending TEXT NOT NULL DEFAULT '',
      version INTEGER NOT NULL,
      summary TEXT NOT NULL,
      note TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS followup_event (
      id INTEGER PRIMARY KEY,
      thread_id INTEGER NOT NULL REFERENCES thread(id),
      version INTEGER NOT NULL,
      actor TEXT NOT NULL,
      action TEXT NOT NULL,
      payload TEXT NOT NULL,
      at TEXT NOT NULL,
      UNIQUE(thread_id,version)
    );
    CREATE TABLE IF NOT EXISTS followup_read (
      thread_id INTEGER NOT NULL REFERENCES thread(id),
      actor TEXT NOT NULL,
      last_message_id INTEGER NOT NULL REFERENCES message(id),
      PRIMARY KEY(thread_id,actor)
    );
    """)


def get(conn, thread_id):
    row = conn.execute("SELECT * FROM followup WHERE thread_id=?", (thread_id,)).fetchone()
    return dict(row) if row else None


def _pause_outreach(conn, thread_id, actor, at):
    """Same transaction as the handoff; cancellation never silently restarts mail."""
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='prospect_sequence'"
    ).fetchone():
        return
    sequences = conn.execute(
        "SELECT DISTINCT s.id FROM prospect_sequence s "
        "JOIN prospect_step p ON p.sequence_id=s.id "
        "JOIN message m ON m.message_id=p.message_id AND m.mailbox_id=s.mailbox_id "
        "WHERE m.thread_id=? AND s.state='active'",
        (thread_id,),
    ).fetchall()
    for sequence in sequences:
        conn.execute(
            "UPDATE prospect_sequence SET state='paused',stop_reason='paused' WHERE id=?",
            (sequence["id"],),
        )
        conn.execute(
            "INSERT INTO prospect_event(sequence_id,type,occurred_at,detail) "
            "VALUES(?,'paused',?,?)",
            (sequence["id"], at, json.dumps({"actor": actor, "reason": "conversation_handoff"})),
        )


def transfer(conn, thread_id, actor, recipient, version, summary, note):
    if actor == recipient:
        raise ValueError("接收人不能是自己")
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = get(conn, thread_id)
        if (current is None and version != 0) or (
            current and (current["version"] != version or current["owner"] != actor)
        ):
            raise PermissionError("负责人或版本已变化，请刷新后重试")
        if current and current["pending"]:
            raise ValueError("已有待接手交接，请先完成或取消")
        at = datetime.now(UTC).isoformat()
        conn.execute(
            "INSERT INTO followup VALUES(?,?,?,?,?,?,?) ON CONFLICT(thread_id) DO UPDATE SET "
            "pending=excluded.pending,version=excluded.version,summary=excluded.summary,"
            "note=excluded.note,updated_at=excluded.updated_at",
            (thread_id, actor, recipient, version + 1, json.dumps(summary), note, at),
        )
        conn.execute(
            "INSERT INTO followup_event(thread_id,version,actor,action,payload,at) "
            "VALUES(?,?,?,?,?,?)",
            (
                thread_id,
                version + 1,
                actor,
                "offer",
                json.dumps({"recipient": recipient, "summary": summary, "note": note}),
                at,
            ),
        )
        _pause_outreach(conn, thread_id, actor, at)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get(conn, thread_id)


def decide(conn, thread_id, actor, version, action):
    if action not in {"accept", "cancel"}:
        raise ValueError("未知交接动作")
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = get(conn, thread_id)
        field = "pending" if action == "accept" else "owner"
        if (
            not current
            or not current["pending"]
            or current["version"] != version
            or current[field] != actor
        ):
            raise PermissionError("交接已变化或无权操作")
        owner = actor if action == "accept" else current["owner"]
        at = datetime.now(UTC).isoformat()
        conn.execute(
            "UPDATE followup SET owner=?,pending='',version=?,updated_at=? WHERE thread_id=?",
            (owner, version + 1, at, thread_id),
        )
        conn.execute(
            "INSERT INTO followup_event(thread_id,version,actor,action,payload,at) "
            "VALUES(?,?,?,?,?,?)",
            (
                thread_id,
                version + 1,
                actor,
                action,
                json.dumps({"previous_owner": current["owner"], "owner": owner}),
                at,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return get(conn, thread_id)
