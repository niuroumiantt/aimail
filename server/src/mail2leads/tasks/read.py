"""给一封来信生成读数并落库。失败也落库——失败必须显形(宪法第六条)。"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime

from mail2leads import backends
from mail2leads.store import history, leads, repo
from mail2leads.tasks import extract_lead as lead_task
from mail2leads.tasks.summarize import TASK_VERSION, compose_source, summarize

log = logging.getLogger("mail2leads.read")


def read_message(conn: sqlite3.Connection, message_pk: int, now: datetime | None = None) -> str:
    """返回 'ok' 或 'failed'。不是询盘的线程移到 invalid。"""
    now = now or datetime.now(UTC)
    row = conn.execute(
        "SELECT mailbox_id, thread_id, subject, body_new, body_quoted FROM message WHERE id = ?",
        (message_pk,),
    ).fetchone()
    if row is None:
        raise KeyError(f"没有 message {message_pk}")
    # 这位客户的往来(M6):同一邮箱里同一地址/同一公司域的其他线程,原文摘录 + 我们记的状态
    past = history.for_thread(conn, int(row["mailbox_id"]), int(row["thread_id"]))
    source = compose_source(row["subject"], row["body_new"], row["body_quoted"], history=past)
    produced_at = now.replace(microsecond=0).isoformat()

    try:
        result = summarize(source)
    except backends.LLMError as exc:
        conn.execute(
            "INSERT INTO message_reading "
            "(source_id, model, task_version, produced_at, status, payload, reason) "
            "VALUES (?, ?, ?, ?, 'failed', '{}', ?)",
            (message_pk, backends.describe(), TASK_VERSION, produced_at, str(exc)[:500]),
        )
        return "failed"

    s = result.summary
    payload = {
        "is_inquiry": s.is_inquiry,
        "language": s.detected_language,
        "summary_zh": s.summary_zh,
        "summary_en": s.summary_en,
        "facts": s.facts,
        "quoted_numbers": s.quoted_numbers,
        "unverified": list(result.unverified),
    }
    conn.execute(
        "INSERT INTO message_reading "
        "(source_id, model, task_version, produced_at, status, payload) "
        "VALUES (?, ?, ?, ?, 'ok', ?)",
        (
            message_pk,
            result.backend,
            TASK_VERSION,
            produced_at,
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    if not s.is_inquiry:
        repo.set_folder(conn, int(row["thread_id"]), "invalid")
        return "ok"
    suggest_lead(conn, message_pk, int(row["thread_id"]), source, produced_at)
    return "ok"


def suggest_lead(
    conn: sqlite3.Connection, message_pk: int, thread_id: int, source: str, produced_at: str
) -> str:
    """询盘 → 线索建议。失败也落一行(status=failed),界面能数出来有几封没提出来。"""
    try:
        result = lead_task.extract_lead(source)
    except backends.LLMError as exc:
        leads.insert_suggestion(
            conn,
            message_pk,
            thread_id,
            backends.describe(),
            lead_task.TASK_VERSION,
            produced_at,
            None,
            str(exc)[:500],
        )
        return "failed"
    payload = {**result.lead.model_dump(), "unverified": list(result.unverified)}
    leads.insert_suggestion(
        conn, message_pk, thread_id, result.backend, lead_task.TASK_VERSION, produced_at, payload
    )
    return "ok"


def unread_incoming(conn: sqlite3.Connection, mailbox_id: int) -> list[int]:
    """还没有读数的来信,按时间先后。"""
    rows = conn.execute(
        "SELECT m.id FROM message m LEFT JOIN message_reading r ON r.source_id = m.id "
        "WHERE m.mailbox_id = ? AND m.direction = 'in' AND r.id IS NULL ORDER BY m.sent_at, m.id",
        (mailbox_id,),
    ).fetchall()
    return [int(r["id"]) for r in rows]
