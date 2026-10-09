"""Attributed storage for user-requested mail-body translations."""

import json
import sqlite3
from datetime import UTC, datetime
from hashlib import sha256

from aimail import backends
from aimail.ingest.quote import readable_body
from aimail.tasks import translate_mail as task
from aimail.translation_layout import cache_source, from_raw

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
        "html_zh": json.loads(row["payload"]).get("html_zh"),
        "layout_notice": "已保存旧版译文；重新翻译可保留表格排版。"
        if row["task_version"] == "translate_mail@1"
        else "",
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
    message = conn.execute(
        "SELECT body_new,body_quoted FROM message WHERE id=?", (source_id,)
    ).fetchone()
    if not message:
        raise LookupError("邮件不存在")
    source = readable_body(message["body_new"], message["body_quoted"]).strip()
    if not source:
        raise ValueError("本封新增正文为空，无法翻译")
    return source


def get_current(conn, source_id):
    """Read a cache for these exact body bytes and task, regardless of provider.

    Old prototype rows have no source hash and cannot verify their input. An
    unchanged successful translation always wins over a later failed attempt.
    """
    source = _source(conn, source_id)
    cache_input = cache_source(source, _layout(conn, source_id, source))
    row = conn.execute(
        "SELECT * FROM message_translation WHERE source_id=? AND "
        "((source_hash=? AND task_version=?) OR "
        "(source_hash=? AND task_version='translate_mail@1')) "
        "ORDER BY (status='ok') DESC,(task_version=?) DESC,produced_at DESC,id DESC LIMIT 1",
        (
            source_id,
            sha256(cache_input.encode()).hexdigest(),
            task.TASK_VERSION,
            sha256(source.encode()).hexdigest(),
            task.TASK_VERSION,
        ),
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
    layout = _layout(conn, source_id, source)
    model = backends.describe(task.routed_model())
    try:
        payload = (
            task.translate_layout(layout) if layout else {"text_zh": task.translate(source).text_zh}
        )
        if not payload["text_zh"].strip():
            raise backends.LLMError("翻译正文为空")
        if task._numbers(source) != task._numbers(payload["text_zh"]):
            raise backends.LLMError("翻译没有完整保留原文中的型号、数字或日期")
        status, reason = "ok", ""
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
            sha256(cache_source(source, layout).encode()).hexdigest(),
        ),
    )
    return status


def _layout(conn, source_id, source):
    if "raw" not in {r["name"] for r in conn.execute("PRAGMA table_info(message)")}:
        return None
    row = conn.execute(
        "SELECT raw,body_new,body_quoted FROM message WHERE id=?", (source_id,)
    ).fetchone()
    from aimail.ingest.quote import readable_parts

    return (
        from_raw(row["raw"], source, readable_parts(row["body_new"], row["body_quoted"])[1])
        if row
        else None
    )
