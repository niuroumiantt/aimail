"""Mailbox-scoped display snapshots; every model input is immutable mail evidence.

Reuse ask_mailbox's versioned, citation-checked task. Independent threads stay
independent; snapshots are never supplied to another model call.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta

from aimail import backends
from aimail.ingest import attachments
from aimail.store import model_selection
from aimail.tasks import ask_mailbox

QUESTION = (
    "综合这个独立话题的全部往来原文，给出当前需求摘要：产品规格、最新数量、报价及交付条件、"
    "客户后续更改、我方已经回复的事项和仍待解决的要求。先列当前需求，再列往来变化。"
    "旧数量被后续邮件更改时，必须说明它是历史要求，不能当作当前数量。"
    "买方采购和供应商供货都按原文说明；日常邮件仅概括实际事项，不编造交易。"
    "每条结论引用其对应原文；跨邮件的信息分成分别可核验的结论，不混入其他话题。"
    "正文或附件缺失、截断时不要声称读完。最多给出六条简明中文结论。"
)
VIEW_VERSION = "customer_workspace@1"
SOURCE_BUDGET = 60_000
LEASE = timedelta(minutes=10)


def _model() -> str:
    try:
        return backends.describe()
    except backends.LLMError:
        return "模型未配置"


def inputs(conn: sqlite3.Connection, thread: sqlite3.Row) -> tuple[str, list[dict], dict]:
    identity, sources, scope = _input_data(conn, thread)
    return _fingerprint(identity), sources, scope


def _fingerprint(identity: list, legacy_model: str | None = None) -> str:
    if legacy_model is not None:
        # customer_workspace@1 previously put the model between source and
        # task identity. Match that exact old key without rewriting attribution.
        identity = [*identity[:4], legacy_model, *identity[4:]]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def _input_data(conn: sqlite3.Connection, thread: sqlite3.Row) -> tuple[list, list[dict], dict]:
    rows = conn.execute(
        "SELECT * FROM message WHERE thread_id=? AND mailbox_id=? ORDER BY sent_at DESC,id DESC",
        (thread["id"], thread["mailbox_id"]),
    ).fetchall()
    manifest = []
    sources = []
    budget = SOURCE_BUDGET
    truncated = unread_attachments = 0
    for row in rows:
        texts = attachments.texts_for_message(conn, int(row["id"]))
        attachment_manifest = [
            tuple(a)
            for a in conn.execute(
                "SELECT a.id,a.sha256,t.id,t.model,t.task_version,t.status,t.text,t.reason "
                "FROM attachment a LEFT JOIN attachment_text t ON t.id="
                "(SELECT id FROM attachment_text WHERE source_id=a.id "
                "ORDER BY produced_at DESC,id DESC LIMIT 1) WHERE a.message_id=? ORDER BY a.id",
                (row["id"],),
            )
        ]
        manifest.append((row["id"], row["raw_sha256"], attachment_manifest))
        unread_attachments += sum(a.status != "ok" for a in texts)
        text = (
            f"Subject: {row['subject']}\nFrom: {row['from_email']}\nTo: {row['to_emails']}\n"
            f"Date: {row['sent_at']}\nDirection: {row['direction']}\n\n{row['body_new']}"
        )
        if row["body_quoted"]:
            text += f"\n\n——邮件内的历史引用——\n{row['body_quoted']}"
        for attachment in texts:
            text += f"\n\n——附件 {attachment.filename}——\n"
            text += attachment.text if attachment.status == "ok" else "附件未读出"
        take = min(len(text), budget)
        if take < len(text):
            truncated += 1
        if take:
            sources.append(
                {
                    "id": int(row["id"]),
                    "thread_id": int(thread["id"]),
                    "subject": row["subject"],
                    "sent_at": row["sent_at"],
                    "text": text[:take],
                }
            )
            budget -= take
    # Entire source/attachment manifest, not just the latest timestamp.
    identity = [
        thread["mailbox_id"],
        thread["id"],
        thread["contact_email"].strip().casefold(),
        sorted(manifest),
        ask_mailbox.TASK_VERSION,
        VIEW_VERSION,
        QUESTION,
        SOURCE_BUDGET,
    ]
    return (
        identity,
        list(reversed(sources)),
        {
            "total": len(rows),
            "included": len(sources),
            "truncated": truncated,
            "unread_attachments": unread_attachments,
        },
    )


def _matching(conn: sqlite3.Connection, thread: sqlite3.Row, identity: list) -> sqlite3.Row | None:
    key = _fingerprint(identity)
    matches = [
        row
        for row in conn.execute(
            "SELECT * FROM customer_summary WHERE source_id=? AND mailbox_id=? "
            "AND task_version=? ORDER BY id DESC",
            (thread["id"], thread["mailbox_id"], ask_mailbox.TASK_VERSION),
        )
        if row["input_hash"] in {key, _fingerprint(identity, row["model"])}
    ]
    # Any successful snapshot of the same inputs can be reused, even when a
    # different provider failed on those inputs later. No automatic provider retry.
    return next((row for row in matches if row["status"] == "ok"), matches[0] if matches else None)


def _threads(
    conn: sqlite3.Connection, mailbox_id: int, contact: str, thread_id: int | None = None
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM thread WHERE mailbox_id=? AND lower(trim(contact_email))=? "
        "AND NOT EXISTS (SELECT 1 FROM thread_mail_state s WHERE s.thread_id=thread.id "
        "AND s.deleted_at<>'') AND (? IS NULL OR thread.id=?) ORDER BY last_at DESC,id DESC",
        (mailbox_id, contact.strip().casefold(), thread_id, thread_id),
    ).fetchall()


def context(
    conn: sqlite3.Connection, mailbox_id: int, contact: str, *, thread_id: int | None = None
) -> dict:
    projects = []
    for thread in _threads(conn, mailbox_id, contact, thread_id):
        identity, _, scope = _input_data(conn, thread)
        current = _matching(conn, thread, identity)
        saved = (
            current
            if current and current["status"] == "ok"
            else conn.execute(
                "SELECT * FROM customer_summary WHERE source_id=? AND mailbox_id=? AND status='ok' "
                "ORDER BY id DESC LIMIT 1",
                (thread["id"], mailbox_id),
            ).fetchone()
        )
        messages = conn.execute(
            "SELECT id,sent_at,direction,from_email,subject FROM message "
            "WHERE mailbox_id=? AND thread_id=? ORDER BY sent_at,id",
            (mailbox_id, thread["id"]),
        ).fetchall()
        stale = saved is not None and (current is None or current["status"] != "ok")
        state = current["status"] if current else "none"
        projects.append(
            {
                "id": str(thread["id"]),
                "subject": thread["subject"],
                "updated_at": thread["last_at"],
                "state": state,
                "stale": stale,
                "scope": scope,
                "error": current["reason"] if current else "",
                "summary": {
                    "model": saved["model"],
                    "task_version": saved["task_version"],
                    "produced_at": saved["produced_at"],
                    **json.loads(saved["payload"]),
                }
                if saved
                else None,
                "messages": [{**dict(m), "id": str(m["id"])} for m in messages],
            }
        )
    with model_selection.use(conn, mailbox_id):
        ready, reason = backends.ready()
    return {"email": contact, "configured": ready, "reason": reason, "projects": projects}


def claim(
    conn: sqlite3.Connection,
    mailbox_id: int,
    contact: str,
    *,
    retry: bool = False,
    backend: str | None = None,
    thread_id: int | None = None,
) -> list[dict]:
    with model_selection.use(conn, mailbox_id, backend=backend):
        return _claim(conn, mailbox_id, contact, retry=retry, thread_id=thread_id)


def _claim(
    conn: sqlite3.Connection,
    mailbox_id: int,
    contact: str,
    *,
    retry: bool,
    thread_id: int | None,
) -> list[dict]:
    jobs = []
    now = datetime.now(UTC)
    cutoff = (now - LEASE).isoformat()
    for thread in _threads(conn, mailbox_id, contact, thread_id):
        identity, sources, scope = _input_data(conn, thread)
        key = _fingerprint(identity)
        if not sources:
            continue
        row = _matching(conn, thread, identity)
        may_retry = row is not None and (
            (row["status"] == "failed" and retry)
            or (row["status"] == "running" and row["produced_at"] < cutoff)
        )
        if row is None or (may_retry and row["input_hash"] != key):
            result = conn.execute(
                "INSERT OR IGNORE INTO customer_summary(mailbox_id,source_id,input_hash,model,"
                "task_version,produced_at,status,payload,reason) "
                "VALUES(?,?,?,?,?,?,'running','{}','')",
                (
                    mailbox_id,
                    thread["id"],
                    key,
                    _model(),
                    ask_mailbox.TASK_VERSION,
                    now.isoformat(),
                ),
            )
        elif may_retry:
            result = conn.execute(
                "UPDATE customer_summary SET status='running',reason='',produced_at=?,model=? "
                "WHERE id=? AND status=? AND produced_at=?",
                (now.isoformat(), _model(), row["id"], row["status"], row["produced_at"]),
            )
        else:
            continue
        if result.rowcount:
            jobs.append(
                {
                    "id": int(thread["id"]),
                    "key": key,
                    "sources": sources,
                    "scope": scope,
                    "lease": now.isoformat(),
                    "backend": backends.backend(),
                    "model": _model(),
                    "raw_model": backends.model_name(),
                }
            )
    return jobs


def generate(job: dict) -> dict:
    # No previous derived result in the task's history or inputs.
    with backends.use_backend(job["backend"], model=job["raw_model"]):
        findings = ask_mailbox.ask(QUESTION, job["sources"], [])
    return {"findings": findings, "scope": job["scope"]}


def finish(conn: sqlite3.Connection, job: dict, payload: dict | None) -> None:
    conn.execute(
        "UPDATE customer_summary SET status=?,payload=?,reason=?,produced_at=? "
        "WHERE source_id=? AND input_hash=? AND status='running' AND produced_at=?",
        (
            "ok" if payload is not None else "failed",
            json.dumps(payload or {}, ensure_ascii=False),
            "" if payload is not None else "需求摘要更新失败，请查看原文或重试。",
            datetime.now(UTC).isoformat(),
            job["id"],
            job["key"],
            job["lease"],
        ),
    )
