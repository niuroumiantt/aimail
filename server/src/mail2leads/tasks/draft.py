"""给线程起草回信并落库;失败也落库(宪法第六条)。草稿针对线程里最后一封来信。"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from mail2leads import backends
from mail2leads.store import history
from mail2leads.tasks import draft_reply as task


def thread_source(
    conn: sqlite3.Connection, thread_id: int, limit_chars: int = 12000
) -> tuple[int, str]:
    """整条线程按时间拼成模型的输入;返回 (最后一封来信的主键, 文本)。核对依据就是这份文本。"""
    rows = conn.execute(
        "SELECT id, direction, from_name, from_email, subject, sent_at, body_new "
        "FROM message WHERE thread_id = ? ORDER BY sent_at, id",
        (thread_id,),
    ).fetchall()
    if not rows:
        raise LookupError("线程里没有信")
    last_in = next((r for r in reversed(rows) if r["direction"] == "in"), rows[-1])
    parts = [f"Subject: {rows[0]['subject']}"]
    for r in rows:
        who = "我方" if r["direction"] == "out" else (r["from_name"] or r["from_email"])
        parts.append(f"--- {who} · {r['sent_at']} ---\n{r['body_new']}")
    text = "\n\n".join(parts)[-limit_chars:]
    mailbox_id = int(
        conn.execute("SELECT mailbox_id FROM thread WHERE id = ?", (thread_id,)).fetchone()[0]
    )
    past = history.for_thread(conn, mailbox_id, thread_id)
    if past:
        text += "\n\n" + past
    return int(last_in["id"]), text


def make_draft(conn: sqlite3.Connection, thread_id: int, now: datetime | None = None) -> int:
    """起一份草稿,返回 reply_draft 主键。"""
    now = now or datetime.now(UTC)
    source_id, source = thread_source(conn, thread_id)
    produced_at = now.replace(microsecond=0).isoformat()
    try:
        result = task.draft_reply(source)
    except backends.LLMError as exc:
        cur = conn.execute(
            "INSERT INTO reply_draft (source_id, thread_id, model, task_version, produced_at, "
            "status, payload, reason) VALUES (?, ?, ?, ?, ?, 'failed', '{}', ?)",
            (
                source_id,
                thread_id,
                backends.describe(),
                task.TASK_VERSION,
                produced_at,
                str(exc)[:500],
            ),
        )
        return int(cur.lastrowid)
    payload = {**result.draft.model_dump(), "unverified": list(result.unverified)}
    cur = conn.execute(
        "INSERT INTO reply_draft (source_id, thread_id, model, task_version, produced_at, "
        "status, payload) VALUES (?, ?, ?, ?, ?, 'ok', ?)",
        (
            source_id,
            thread_id,
            result.backend,
            task.TASK_VERSION,
            produced_at,
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    return int(cur.lastrowid)


def latest_draft(conn: sqlite3.Connection, thread_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM reply_draft WHERE thread_id = ? ORDER BY produced_at DESC, id DESC LIMIT 1",
        (thread_id,),
    ).fetchone()
