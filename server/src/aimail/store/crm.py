"""Human-confirmed CRM outbox. Downstream receipts never alter mail or confirmed facts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from aimail.store import repo
from aimail.store.company_identity import domain, matches
from aimail.tasks.register_contact import Fields


class Registration(Fields):
    company_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,150}$")
    new_company_reason: str = Field(default="", max_length=500)
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
        "lower(from_email)=lower(?) ORDER BY sent_at DESC,id DESC LIMIT 1",
        (tid, thread["contact_email"]),
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
        if draft.get("fields"):
            draft["fields"]["contact"] = first[0] if first else ""
            draft["fields"]["email"] = thread["contact_email"]
            draft["citations"] = {
                k: v for k, v in draft.get("citations", {}).items() if k not in {"contact", "email"}
            }
    host = domain(thread["contact_email"])
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
            "website": "https://" + host if host else "",
            "company_id": None,
            "new_company_reason": "",
            "next_step": "",
            "due_at": "",
            "link_registration_id": None,
        },
        "candidates": candidates,
        "website_inferred": bool(host),
    }


def identity_check(conn, fields):
    row = conn.execute("SELECT * FROM crm_company_directory WHERE id=1").fetchone()
    current = (
        bool(row)
        and (datetime.now(UTC) - datetime.fromisoformat(row["received_at"])).total_seconds() < 300
    )
    items = json.loads(row["payload"]) if row else []
    candidates = matches(items, fields)
    strong = {v["company_id"] for v in candidates if v["strong"]}
    selected = fields.get("company_id")
    return {
        "current": current,
        "matches": candidates,
        "conflict": len(strong) > 1 or bool(selected and strong and selected not in strong),
        "received_at": row["received_at"] if row else None,
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
        stored = json.loads(current["payload"])
        retry = {k: v for k, v in data.items() if k in stored}
        if current["fingerprint"] != digest and not (
            fingerprint(retry) == current["fingerprint"]
            and all(v in (None, "") for k, v in data.items() if k not in stored)
        ):
            raise ValueError("此话题已经建档，请在客户档案查看和维护")
        return state(conn, tid)
    check = identity_check(conn, data)
    if not check["current"]:
        raise ValueError("公司查重目录尚未就绪或已过期，请稍后刷新")
    if check["conflict"]:
        raise ValueError("企业邮箱与官网匹配到不同公司，请核实后再建档")
    strong = {v["company_id"] for v in check["matches"] if v["strong"]}
    if strong and data["company_id"] not in strong:
        raise ValueError("已找到同一企业，请先选择关联已有公司")
    if (
        check["matches"]
        and not strong
        and not data["company_id"]
        and not data["new_company_reason"].strip()
    ):
        raise ValueError("存在相似公司，请选择已有档案或填写不同公司的核实说明")
    if data["company_id"] and data["company_id"] not in {v["company_id"] for v in check["matches"]}:
        raise ValueError("关联公司不在本次查重结果中，请刷新")
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
        "version": "contact-registration@2"
        if "company_id" in json.loads(row["payload"])
        else "contact-registration@1",
        "id": row["id"],
        "fingerprint": row["fingerprint"],
        "fields": json.loads(row["payload"]),
        "confirmed_by": row["confirmed_by"],
        "confirmed_at": row["confirmed_at"],
        "source": {"mailbox": mailbox, "thread_id": str(row["thread_id"]), "subject": thread},
        "extraction": dict(suggestion) if suggestion else None,
    }
