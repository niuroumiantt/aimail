"""Attributed storage for user-requested mail-body translations."""

import json
import sqlite3
from datetime import UTC, datetime
from hashlib import sha256

from aimail import backends
from aimail.tasks import translate_mail as task

FAILURE_REASON = "翻译未完成，请保留原文，稍后可重试。"


def prepare(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS message_translation (
        id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES message(id),
        model TEXT NOT NULL, task_version TEXT NOT NULL, produced_at TEXT NOT NULL,
        status TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}',
        reason TEXT NOT NULL DEFAULT '', source_hash TEXT NOT NULL DEFAULT '')"""
    )
    if "source_hash" not in {
        row["name"] for row in conn.execute("PRAGMA table_info(message_translation)")
    }:
        try:
            conn.execute(
                "ALTER TABLE message_translation ADD COLUMN source_hash TEXT NOT NULL DEFAULT ''"
            )
        except sqlite3.OperationalError:
            # A second application process may have finished the same migration.
            if "source_hash" not in {
                row["name"] for row in conn.execute("PRAGMA table_info(message_translation)")
            }:
                raise
    conn.execute(
        "CREATE INDEX IF NOT EXISTS translation_by_source "
        "ON message_translation(source_id, produced_at DESC)"
    )


def _out(row):
    if not row:
        return None
    return {
        "status": row["status"],
        "text_zh": json.loads(row["payload"]).get("text_zh", ""),
        "model": row["model"],
        "task_version": row["task_version"],
        "produced_at": row["produced_at"],
        # Neither upstream exceptions nor old prototype diagnostics are public data.
        "reason": FAILURE_REASON if row["status"] == "failed" else "",
        "coverage": "当前邮件新增正文；不含折叠的引用历史与附件",
    }


def get(conn, source_id):
    """Prototype history: return the most recent attempt, including a failure."""
    row = conn.execute(
        "SELECT * FROM message_translation WHERE source_id=? "
        "ORDER BY produced_at DESC,id DESC LIMIT 1",
        (source_id,),
    ).fetchone()
    return _out(row)


def _source(conn, source_id):
    message = conn.execute("SELECT body_new FROM message WHERE id=?", (source_id,)).fetchone()
    if not message:
        raise LookupError("邮件不存在")
    source = message["body_new"].strip()
    if not source:
        raise ValueError("本封新增正文为空，无法翻译")
    return source


def get_current(conn, source_id):
    """Read a cache for these exact body bytes and task, regardless of provider.

    Old prototype rows have no source hash and cannot verify their input. An
    unchanged successful translation always wins over a later failed attempt.
    """
    source = _source(conn, source_id)
    row = conn.execute(
        "SELECT * FROM message_translation WHERE source_id=? AND source_hash=? "
        "AND task_version=? ORDER BY (status='ok') DESC,produced_at DESC,id DESC LIMIT 1",
        (source_id, sha256(source.encode()).hexdigest(), task.TASK_VERSION),
    ).fetchone()
    return _out(row)


def translate_cached(conn, source_id):
    cached = get_current(conn, source_id)
    if cached and cached["status"] == "ok":
        return cached
    translate(conn, source_id)
    return get_current(conn, source_id)


def translate(conn, source_id):
    source = _source(conn, source_id)
    model = backends.describe(task.routed_model())
    try:
        output = task.translate(source)
        if not output.text_zh.strip():
            raise backends.LLMError("翻译正文为空")
        if task._numbers(source) != task._numbers(output.text_zh):
            raise backends.LLMError("翻译没有完整保留原文中的型号、数字或日期")
        status, payload, reason = "ok", {"text_zh": output.text_zh}, ""
    except Exception:
        status, payload, reason = "failed", {}, FAILURE_REASON
    conn.execute(
        "INSERT INTO message_translation"
        "(source_id,model,task_version,produced_at,status,payload,reason,source_hash) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (
            source_id,
            model,
            task.TASK_VERSION,
            datetime.now(UTC).isoformat(),
            status,
            json.dumps(payload, ensure_ascii=False),
            reason,
            sha256(source.encode()).hexdigest(),
        ),
    )
    return status
