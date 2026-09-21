"""Attributed storage for user-requested mail-body translations."""

import json
from datetime import UTC, datetime

from mail2leads import backends
from mail2leads.tasks import translate_mail as task


def prepare(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS message_translation (
        id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES message(id),
        model TEXT NOT NULL, task_version TEXT NOT NULL, produced_at TEXT NOT NULL,
        status TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}',
        reason TEXT NOT NULL DEFAULT '')"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS translation_by_source "
        "ON message_translation(source_id, produced_at DESC)"
    )


def get(conn, source_id):
    row = conn.execute(
        "SELECT * FROM message_translation WHERE source_id=? "
        "ORDER BY produced_at DESC,id DESC LIMIT 1",
        (source_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "status": row["status"],
        "text_zh": json.loads(row["payload"]).get("text_zh", ""),
        "model": row["model"],
        "task_version": row["task_version"],
        "produced_at": row["produced_at"],
        "reason": row["reason"],
        "coverage": "当前邮件新增正文；不含折叠的引用历史与附件",
    }


def translate(conn, source_id):
    message = conn.execute("SELECT body_new FROM message WHERE id=?", (source_id,)).fetchone()
    if not message:
        raise LookupError("邮件不存在")
    source = message["body_new"].strip()
    if not source:
        raise ValueError("本封新增正文为空，无法翻译")
    try:
        output = task.translate(source)
        status, payload, reason = "ok", {"text_zh": output.text_zh}, ""
    except Exception as exc:
        detail = str(exc).strip().replace("\n", " ")[:220]
        status, payload, reason = (
            "failed",
            {},
            f"翻译未完成（{type(exc).__name__}）：{detail or '未显示占位译文'}",
        )
    conn.execute(
        "INSERT INTO message_translation"
        "(source_id,model,task_version,produced_at,status,payload,reason) "
        "VALUES(?,?,?,?,?,?,?)",
        (
            source_id,
            backends.describe(task.routed_model()),
            task.TASK_VERSION,
            datetime.now(UTC).isoformat(),
            status,
            json.dumps(payload, ensure_ascii=False),
            reason,
        ),
    )
    return status
