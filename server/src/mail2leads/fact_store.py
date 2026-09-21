"""Durable automatic extraction queue. Originals and confirmed leads are untouched."""

import hashlib
import json
from datetime import UTC, datetime

from mail2leads import backends
from mail2leads.tasks import extract_mail_facts as task


def prepare(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS mail_fact_reading (
        id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES message(id),
        model TEXT NOT NULL, task_version TEXT NOT NULL, produced_at TEXT NOT NULL,
        status TEXT NOT NULL, input_hash TEXT NOT NULL DEFAULT '',
        payload TEXT NOT NULL DEFAULT '[]', reason TEXT NOT NULL DEFAULT '',
        UNIQUE(source_id, task_version))""")
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(mail_fact_reading)")}
    if "source_scope" not in columns:
        conn.execute(
            "ALTER TABLE mail_fact_reading ADD COLUMN source_scope TEXT NOT NULL DEFAULT 'new_body'"
        )
    conn.execute(
        """INSERT OR IGNORE INTO mail_fact_reading
        (source_id, model, task_version, produced_at, status)
        SELECT id, '', ?, ?, 'queued' FROM message""",
        (task.TASK_VERSION, datetime.now(UTC).isoformat()),
    )


def get(conn, source_id):
    row = conn.execute(
        "SELECT * FROM mail_fact_reading WHERE source_id=? AND task_version=?",
        (source_id, task.TASK_VERSION),
    ).fetchone()
    if not row:
        return None
    return {
        "status": row["status"],
        "facts": json.loads(row["payload"]),
        "model": row["model"],
        "task_version": row["task_version"],
        "produced_at": row["produced_at"],
        "source_id": source_id,
        "reason": row["reason"],
        "coverage": (
            "引用历史首次提取；未含附件；后续转发不会再次读取相同历史"
            if row["source_scope"] == "quoted_bootstrap"
            else "本封新增正文与邮件头；未含附件、引用历史；AI 提取待核对"
        ),
    }


def counts(conn):
    return {
        r["status"]: r["n"]
        for r in conn.execute(
            "SELECT status,COUNT(*) n FROM mail_fact_reading WHERE task_version=? GROUP BY status",
            (task.TASK_VERSION,),
        )
    }


def process(conn, source_id):
    existing = get(conn, source_id)
    if existing and existing["status"] == "ok":
        return "ok"
    m = conn.execute("SELECT * FROM message WHERE id=?", (source_id,)).fetchone()
    new_source = (
        f"Direction: {m['direction']}\nFrom: {m['from_name']} <{m['from_email']}>\n"
        f"To: {m['to_emails']}\nSubject: {m['subject']}\n\n{m['body_new']}"
    )
    use_quote = len(m["body_new"].strip()) < 160 and len(m["body_quoted"].strip()) > 300
    source = (
        "Historical quoted content, being indexed once for this forwarded mail:\n"
        + m["body_quoted"]
        if use_quote
        else new_source
    )
    source_scope = "quoted_bootstrap" if use_quote else "new_body"
    digest = hashlib.sha256(source.encode()).hexdigest()
    conn.execute(
        "UPDATE mail_fact_reading SET status='running',input_hash=?,source_scope=? "
        "WHERE source_id=? AND task_version=?",
        (digest, source_scope, source_id, task.TASK_VERSION),
    )
    try:
        cached = conn.execute(
            "SELECT payload,model FROM mail_fact_reading WHERE input_hash=? AND task_version=? "
            "AND status='ok' AND source_id IN "
            "(SELECT id FROM message WHERE mailbox_id=?) LIMIT 1",
            (digest, task.TASK_VERSION, m["mailbox_id"]),
        ).fetchone()
        if len(source) > 48000:
            raise ValueError("正文过长，等待分段处理；未静默截断")
        facts = json.loads(cached["payload"]) if cached else task.extract(source)
        model = cached["model"] if cached else backends.describe()
        status, reason = "ok", ""
    except Exception as exc:
        model = backends.describe()
        facts, status, reason = (
            [],
            "failed",
            f"提取未完成（{type(exc).__name__}）；可重试，未生成占位结果",
        )
    conn.execute(
        "UPDATE mail_fact_reading SET status=?,payload=?,reason=?,model=?,produced_at=? "
        "WHERE source_id=? AND task_version=?",
        (
            status,
            json.dumps(facts, ensure_ascii=False),
            reason,
            model,
            datetime.now(UTC).isoformat(),
            source_id,
            task.TASK_VERSION,
        ),
    )
    return status
