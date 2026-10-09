"""Human-confirmed CRM outbox. Downstream receipts never alter mail or confirmed facts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from aimail.store import repo
from aimail.tasks.register_contact import Fields


class Registration(Fields):
    email: str = Field(min_length=3, max_length=254)
    next_step: str = Field(default="", max_length=500)
    due_at: str = Field(default="", max_length=10)
    link_registration_id: int | None = Field(default=None, ge=1)

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        value = value.strip().casefold()
        if value.count("@") != 1 or any(c.isspace() for c in value) or not all(value.split("@")):
            raise ValueError("联系邮箱无效")
        return value

    @field_validator("website")
    @classmethod
    def website_valid(cls, value):
        value = value.strip()
        if not value:
            return ""
        if "://" not in value:
            if ":" in value:
                raise ValueError("官网只接受 http/https 网址")
            value = "https://" + value
        url = urlsplit(value)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise ValueError("官网只接受 http/https 网址")
        return value

    @field_validator("due_at")
    @classmethod
    def date_valid(cls, value):
        if value:
            datetime.strptime(value, "%Y-%m-%d")
        return value


def fingerprint(payload):
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def sources(conn, tid):
    rows = conn.execute(
        "SELECT "
        "id,from_name,from_email,to_emails,subject,sent_at,direction,body_new,body_quoted "
        "FROM message WHERE thread_id=? ORDER BY sent_at DESC,id DESC",
        (tid,),
    ).fetchall()
    result, budget = [], 40000
    for r in rows:
        text = (
            f"From: {r['from_name']} <{r['from_email']}>\nTo: {r['to_emails']}\n"
            f"Subject: {r['subject']}\nDate: {r['sent_at']}\n"
            f"Direction: {r['direction']}\n{r['body_new']}\n引用历史:\n{r['body_quoted']}"
        )
        if budget <= 0:
            break
        result.append({"id": r["id"], "text": text[:budget]})
        budget -= len(result[-1]["text"])
    return result


def state(conn, tid):
    thread = conn.execute("SELECT * FROM thread WHERE id=?", (tid,)).fetchone()
    row = conn.execute("SELECT * FROM crm_registration WHERE thread_id=?", (tid,)).fetchone()
    suggestion = conn.execute("SELECT * FROM crm_suggestion WHERE thread_id=?", (tid,)).fetchone()
    first = conn.execute(
        "SELECT from_name FROM message WHERE thread_id=? AND "
        "direction='in' ORDER BY sent_at DESC,id DESC LIMIT 1",
        (tid,),
    ).fetchone()
    candidates = []
    for item in conn.execute(
        "SELECT * FROM crm_registration WHERE mailbox_id=? AND thread_id<>?",
        (thread["mailbox_id"], tid),
    ):
        facts, receipt = json.loads(item["payload"]), json.loads(item["receipt"])
        if receipt and facts["email"] == thread["contact_email"].strip().casefold():
            candidates.append({"id": item["id"], "company": facts["company"] or facts["email"]})
    draft = None
    if suggestion:
        draft = {
            "status": suggestion["status"],
            "model": suggestion["model"],
            "task_version": suggestion["task_version"],
            "produced_at": suggestion["produced_at"],
            "source_id": suggestion["source_id"],
            "stale": suggestion["input_hash"] != fingerprint(sources(conn, tid)),
            **json.loads(suggestion["payload"]),
        }
        if (
            draft["status"] == "running"
            and (datetime.now(UTC) - datetime.fromisoformat(draft["produced_at"])).total_seconds()
            > 600
        ):
            draft = {**draft, "status": "failed", "error": "提取已超时，可以重试或手动填写"}
    return {
        "registration": {
            "id": row["id"],
            "fields": json.loads(row["payload"]),
            "receipt": json.loads(row["receipt"]),
            "confirmed_at": row["confirmed_at"],
        }
        if row
        else None,
        "suggestion": draft,
        "defaults": {
            **Fields().model_dump(),
            "contact": first[0] if first else "",
            "email": thread["contact_email"],
            "next_step": "",
            "due_at": "",
            "link_registration_id": None,
        },
        "candidates": candidates,
    }


def save(conn, tid, mid, payload: Registration, actor):
    if not actor.strip():
        raise PermissionError("建档必须由人确认")
    data = payload.model_dump()
    if data["link_registration_id"] is not None:
        linked = conn.execute(
            "SELECT * FROM crm_registration WHERE id=? AND mailbox_id=?",
            (data["link_registration_id"], mid),
        ).fetchone()
        if not linked or not json.loads(linked["receipt"]):
            raise ValueError("关联档案不存在或尚未同步")
    digest = fingerprint(data)
    current = conn.execute("SELECT * FROM crm_registration WHERE thread_id=?", (tid,)).fetchone()
    if current:
        if current["fingerprint"] != digest:
            raise ValueError("此话题已经建档，请在客户档案查看和维护")
        return state(conn, tid)
    at = repo.now_iso()
    conn.execute(
        "INSERT INTO "
        "crm_registration(thread_id,mailbox_id,payload,fingerprint,confirmed_by,confirmed_at) "
        "VALUES(?,?,?,?,?,?)",
        (tid, mid, json.dumps(data, ensure_ascii=False), digest, actor, at),
    )
    return state(conn, tid)


def exported(conn, row):
    mailbox = conn.execute(
        "SELECT address FROM mailbox WHERE id=?", (row["mailbox_id"],)
    ).fetchone()[0]
    thread = conn.execute("SELECT subject FROM thread WHERE id=?", (row["thread_id"],)).fetchone()[
        0
    ]
    suggestion = conn.execute(
        "SELECT payload,model,task_version,produced_at,source_id FROM "
        "crm_suggestion WHERE thread_id=? AND status='ok'",
        (row["thread_id"],),
    ).fetchone()
    return {
        "version": "contact-registration@1",
        "id": row["id"],
        "fingerprint": row["fingerprint"],
        "fields": json.loads(row["payload"]),
        "confirmed_by": row["confirmed_by"],
        "confirmed_at": row["confirmed_at"],
        "source": {"mailbox": mailbox, "thread_id": str(row["thread_id"]), "subject": thread},
        "extraction": dict(suggestion) if suggestion else None,
    }
