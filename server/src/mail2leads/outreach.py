"""Human-approved, fixed-content prospect sequences; importing never authorizes sending.

One poller per service. SMTP cannot guarantee exactly-once: a persisted in-flight
attempt left by a crash becomes unknown and is never automatically retried.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from email import policy
from email.parser import BytesParser
from urllib.parse import urlsplit

from mail2leads.ingest.run import store_raw
from mail2leads.send import build_message

CADENCE = [0, 7, 14, 28, 60, 90]
EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}")
SCHEMA = """
CREATE TABLE IF NOT EXISTS prospect_sequence (
 id TEXT PRIMARY KEY, mailbox_id INTEGER NOT NULL REFERENCES mailbox(id),
 external_id TEXT NOT NULL, idem_key TEXT NOT NULL, email TEXT NOT NULL,
 payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL,
 approved_by TEXT, approved_at TEXT, approval_hash TEXT, first_sent_at TEXT,
 stop_reason TEXT NOT NULL DEFAULT '',
 UNIQUE(mailbox_id,idem_key), UNIQUE(mailbox_id,email), UNIQUE(mailbox_id,external_id)
);
CREATE TABLE IF NOT EXISTS prospect_step (
 sequence_id TEXT NOT NULL REFERENCES prospect_sequence(id), day INTEGER NOT NULL,
 subject TEXT NOT NULL, body TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
 message_id TEXT, raw BLOB, attempted_at TEXT, sent_at TEXT,
 PRIMARY KEY(sequence_id,day)
);
CREATE TABLE IF NOT EXISTS prospect_event (
 id INTEGER PRIMARY KEY, sequence_id TEXT NOT NULL REFERENCES prospect_sequence(id),
 type TEXT NOT NULL, occurred_at TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prospect_assignment (
 sequence_id TEXT PRIMARY KEY REFERENCES prospect_sequence(id),
 owner TEXT NOT NULL, pending TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL
);
"""


def stamp(now=None):
    return (now or datetime.now(UTC)).isoformat()


def init(conn):
    conn.executescript(SCHEMA)


@contextmanager
def transaction(conn):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def event(conn, sid, kind, detail=None, now=None):
    conn.execute(
        "INSERT INTO prospect_event(sequence_id,type,occurred_at,detail) VALUES(?,?,?,?)",
        (sid, kind, stamp(now), json.dumps(detail or {}, ensure_ascii=False)),
    )


def import_prospect(conn, mailbox_id, payload):
    if payload.get("cadence_days") != CADENCE or payload.get("schema_version") != "1":
        raise ValueError("不支持的协议或时间表")
    for field, size in (
        ("external_id", 100),
        ("idempotency_key", 300),
        ("company", 250),
        ("email", 254),
        ("country", 80),
        ("tier", 10),
        ("policy_version", 100),
    ):
        value = payload.get(field)
        if not isinstance(value, str) or not 1 <= len(value) <= size:
            raise ValueError("名单字段缺失或过长")
    address = payload["email"].strip().casefold()
    if not EMAIL.fullmatch(address) or ".." in address:
        raise ValueError("邮箱格式不正确")
    for url in (payload.get("website"), payload.get("source", {}).get("url")):
        if not isinstance(url, str) or len(url) > 2048:
            raise ValueError("缺少公开来源")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            raise ValueError("来源地址不合法")
    if len(json.dumps(payload)) > 24000:
        raise ValueError("名单载荷过大")
    with transaction(conn):
        rows = conn.execute(
            "SELECT * FROM prospect_sequence WHERE mailbox_id=? AND "
            "(idem_key=? OR email=? OR external_id=?)",
            (mailbox_id, payload["idempotency_key"], address, payload["external_id"]),
        ).fetchall()
        if rows:
            row = rows[0]
            if (
                len(rows) != 1
                or row["email"] != address
                or row["external_id"] != payload["external_id"]
            ):
                raise ValueError("同一客户或邮箱已导入，请核对已有记录")
            if json.loads(row["payload"]) != payload:
                raise ValueError("幂等键对应的载荷发生变化")
            sid = row["id"]
        else:
            sid = "ps_" + uuid.uuid4().hex
            conn.execute(
                "INSERT INTO prospect_sequence "
                "(id,mailbox_id,external_id,idem_key,email,payload,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    sid,
                    mailbox_id,
                    payload["external_id"],
                    payload["idempotency_key"],
                    address,
                    json.dumps(payload, ensure_ascii=False),
                    stamp(),
                ),
            )
            event(conn, sid, "imported")
    return {"receipt_id": sid, "external_id": payload["external_id"], "status": "imported"}


def get(conn, mailbox_id, sid):
    row = conn.execute(
        "SELECT * FROM prospect_sequence WHERE id=? AND mailbox_id=?", (sid, mailbox_id)
    ).fetchone()
    if row is None:
        raise ValueError("找不到开发信序列")
    return row


def assign(conn, mailbox_id, sid, actor, default_owner, action, recipient, version):
    """Pre-contact handoff only. Assignment never approves content or schedules mail."""
    with transaction(conn):
        sequence = get(conn, mailbox_id, sid)
        if sequence["state"] != "draft":
            raise ValueError("仅可在首次批准发送前分配；已联系客户请使用邮件会话交接")
        current = conn.execute(
            "SELECT * FROM prospect_assignment WHERE sequence_id=?", (sid,)
        ).fetchone()
        owner = current["owner"] if current else default_owner
        pending = current["pending"] if current else ""
        old_version = current["version"] if current else 0
        if version != old_version:
            raise ValueError("分配记录已变化，请刷新")
        if action == "offer":
            if actor != owner or pending or not recipient or recipient == actor:
                raise PermissionError("无权分配或已有待接手记录")
            pending = recipient
        elif action == "accept":
            if not pending or actor != pending:
                raise PermissionError("只有指定接收人可以接手")
            owner, pending = actor, ""
        elif action == "cancel":
            if actor != owner or not pending:
                raise PermissionError("只有负责人可以取消待接手记录")
            pending = ""
        else:
            raise ValueError("未知分配动作")
        conn.execute(
            "INSERT INTO prospect_assignment VALUES(?,?,?,?) ON CONFLICT(sequence_id) "
            "DO UPDATE SET owner=excluded.owner,pending=excluded.pending,version=excluded.version",
            (sid, owner, pending, version + 1),
        )
        event(
            conn,
            sid,
            "assignment",
            {
                "actor": actor,
                "action": action,
                "owner": owner,
                "pending": pending,
                "version": version + 1,
            },
        )
    return {"owner": owner, "pending": pending, "version": version + 1}


def approve(conn, mailbox_id, sid, actor, steps, policy_confirmed, now=None, *, sender=""):
    sender = (
        sender
        or conn.execute("SELECT address FROM mailbox WHERE id=?", (mailbox_id,)).fetchone()[0]
    )
    if not EMAIL.fullmatch(sender):
        raise ValueError("必须先配置完整且已核验的发件地址")
    if not actor or not policy_confirmed:
        raise ValueError("需要人工确认完整内容和适用发送政策")
    if not isinstance(steps, list) or [s.get("day") for s in steps] != CADENCE:
        raise ValueError("必须确认首封及第 7、14、28、60、90 天的六封内容")
    for step in steps:
        for key, limit in (("subject", 200), ("body", 12000)):
            value = step.get(key)
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
                raise ValueError("标题或正文为空或过长")
        if "\r" in step["subject"] or "\n" in step["subject"]:
            raise ValueError("标题不能包含换行")
    with transaction(conn):
        row = get(conn, mailbox_id, sid)
        assigned = conn.execute(
            "SELECT owner FROM prospect_assignment WHERE sequence_id=?", (sid,)
        ).fetchone()
        if assigned and assigned["owner"].casefold() != sender.casefold():
            raise PermissionError("发件身份不是当前潜客负责人")
        if row["state"] != "draft":
            raise ValueError("已批准或停止的序列不可覆盖或重复启用")
        approval = json.dumps(
            {"email": row["email"], "sender": sender, "steps": steps}, sort_keys=True
        )
        digest = hashlib.sha256(approval.encode()).hexdigest()
        for step in steps:
            conn.execute(
                "INSERT INTO prospect_step(sequence_id,day,subject,body) VALUES(?,?,?,?)",
                (sid, step["day"], step["subject"], step["body"]),
            )
        conn.execute(
            "UPDATE prospect_sequence SET state='active',approved_by=?,approved_at=?,"
            "approval_hash=? WHERE id=?",
            (actor, stamp(now), digest, sid),
        )
        event(conn, sid, "approved", {"actor": actor, "content_hash": digest}, now)


def stop(conn, mailbox_id, sid, reason, actor="system", now=None):
    if reason not in {"paused", "replied", "unsubscribed", "bounced", "delivery_unknown"}:
        raise ValueError("无效停发原因")
    row = get(conn, mailbox_id, sid)
    if row["state"] in {"unsubscribed", "bounced"} or row["state"] == reason:
        return
    conn.execute(
        "UPDATE prospect_sequence SET state=?,stop_reason=? WHERE id=?", (reason, reason, sid)
    )
    event(conn, sid, reason, {"actor": actor}, now)


def recover(conn, mailbox_id):
    with transaction(conn):
        rows = conn.execute(
            "SELECT DISTINCT s.id FROM prospect_sequence s JOIN prospect_step p "
            "ON p.sequence_id=s.id WHERE s.mailbox_id=? AND p.state='sending'",
            (mailbox_id,),
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE prospect_step SET state='delivery_unknown' "
                "WHERE sequence_id=? AND state='sending'",
                (row["id"],),
            )
            stop(conn, mailbox_id, row["id"], "delivery_unknown")


def inbound_reason(conn, row):
    """Any reply pauses. Delivery status uses RFC report fields, never keyword intent guesses."""
    mids = {
        r[0]
        for r in conn.execute(
            "SELECT message_id FROM prospect_step WHERE sequence_id=? AND message_id IS NOT NULL",
            (row["id"],),
        )
    }
    messages = conn.execute(
        "SELECT from_email,in_reply_to,refs,raw FROM message "
        "WHERE mailbox_id=? AND direction='in' AND received_at>=?",
        (row["mailbox_id"], row["created_at"][:19]),
    )
    for message in messages:
        parsed = BytesParser(policy=policy.default).parsebytes(message["raw"])
        for part in parsed.walk():
            if part.get_content_type() != "message/delivery-status":
                continue
            blocks = part.get_payload()
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                recipient = str(block.get("Final-Recipient", "")).split(";")[-1].strip().lower()
                if recipient == row["email"]:
                    return (
                        "bounced" if str(block.get("Action", "")).lower() == "failed" else "paused"
                    )
        if message["from_email"].casefold() == row["email"]:
            return "replied"
        references = set((message["refs"] or "").split()) | {message["in_reply_to"]}
        if mids & references:
            return "replied"
    return ""


def tick(
    conn, mailbox_id, *, sender, sender_name, transport, enabled=False, now=None, daily_cap=20
):
    """Call only after a successful fresh INBOX sync. Send at most one email per tick."""
    now = now or datetime.now(UTC)
    # Stops are evaluated even if today's budget is exhausted.
    with transaction(conn):
        rows = conn.execute(
            "SELECT * FROM prospect_sequence WHERE mailbox_id=? "
            "AND state IN ('active','completed') "
            "ORDER BY approved_at",
            (mailbox_id,),
        ).fetchall()
        for row in rows:
            reason = inbound_reason(conn, row)
            if reason:
                stop(conn, mailbox_id, row["id"], reason, now=now)
        if not enabled or not EMAIL.fullmatch(sender):
            return False
        used = conn.execute(
            "SELECT COUNT(*) FROM prospect_step p JOIN prospect_sequence s ON s.id=p.sequence_id "
            "WHERE s.mailbox_id=? AND p.attempted_at>=?",
            (mailbox_id, stamp(now.replace(hour=0, minute=0, second=0, microsecond=0))),
        ).fetchone()[0]
        if used >= max(0, daily_cap):
            return False
        selected = None
        for row in rows:
            if get(conn, mailbox_id, row["id"])["state"] != "active":
                continue
            steps = conn.execute(
                "SELECT * FROM prospect_step WHERE sequence_id=? ORDER BY day", (row["id"],)
            ).fetchall()
            if any(s["state"] in {"sending", "delivery_unknown"} for s in steps):
                continue
            bound = [{"day": s["day"], "subject": s["subject"], "body": s["body"]} for s in steps]
            digest = hashlib.sha256(
                json.dumps(
                    {"email": row["email"], "sender": sender, "steps": bound}, sort_keys=True
                ).encode()
            ).hexdigest()
            if digest != row["approval_hash"]:
                stop(conn, mailbox_id, row["id"], "paused", now=now)
                continue
            anchor = datetime.fromisoformat(row["first_sent_at"]) if row["first_sent_at"] else now
            due = [
                s
                for s in steps
                if s["state"] == "pending" and anchor + timedelta(days=s["day"]) <= now
            ]
            if not due:
                continue
            selected = (row, due[-1])
            for missed in due[:-1]:
                conn.execute(
                    "UPDATE prospect_step SET state='skipped_late' WHERE sequence_id=? AND day=?",
                    (row["id"], missed["day"]),
                )
                event(conn, row["id"], "skipped_late", {"day": missed["day"]}, now)
            break
        if not selected:
            return False
        row, step = selected
        first = conn.execute(
            "SELECT message_id FROM prospect_step WHERE sequence_id=? AND day=0", (row["id"],)
        ).fetchone()[0]
        msg, mid = build_message(
            sender=sender,
            sender_name=sender_name,
            to=[row["email"]],
            subject=step["subject"],
            body=step["body"],
            in_reply_to=first or "",
            references="",
            now=now,
        )
        raw = msg.as_bytes()
        conn.execute(
            "UPDATE prospect_step SET state='sending',message_id=?,raw=?,attempted_at=? "
            "WHERE sequence_id=? AND day=?",
            (mid, raw, stamp(now), row["id"], step["day"]),
        )
        event(conn, row["id"], "sending", {"day": step["day"], "message_id": mid}, now)
    # Durable attempt is committed before SMTP. Recheck stop state right before sending.
    if get(conn, mailbox_id, row["id"])["state"] != "active":
        return False
    try:
        result = transport.deliver(sender, [row["email"]], raw)
        if result != "ok":
            raise RuntimeError("transport_not_accepted")
        pk, _ = store_raw(conn, mailbox_id, raw, "out", now)
        if pk is None:
            raise RuntimeError("message_not_persisted")
        with transaction(conn):
            thread_id = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[
                0
            ]
            conn.execute(
                "INSERT INTO outbound(mailbox_id,thread_id,message_pk,sent_by,sent_at,"
                "transport_result) VALUES(?,?,?,?,?,?)",
                (mailbox_id, thread_id, pk, row["approved_by"], stamp(now), "ok"),
            )
            conn.execute(
                "UPDATE prospect_step SET state='smtp_accepted',sent_at=? "
                "WHERE sequence_id=? AND day=?",
                (stamp(now), row["id"], step["day"]),
            )
            conn.execute(
                "UPDATE prospect_sequence SET first_sent_at=COALESCE(first_sent_at,?) WHERE id=?",
                (stamp(now), row["id"]),
            )
            if step["day"] == 90:
                conn.execute(
                    "UPDATE prospect_sequence SET state='completed' WHERE id=? AND state='active'",
                    (row["id"],),
                )
            event(
                conn,
                row["id"],
                "smtp_accepted",
                {"day": step["day"], "message_id": mid, "thread_id": thread_id},
                now,
            )
    except Exception:
        with transaction(conn):
            conn.execute(
                "UPDATE prospect_step SET state='delivery_unknown' WHERE sequence_id=? AND day=?",
                (row["id"], step["day"]),
            )
            stop(conn, mailbox_id, row["id"], "delivery_unknown", now=now)
        return False
    return True


def events(conn, mailbox_id, after=0):
    rows = conn.execute(
        "SELECT e.*,s.external_id FROM prospect_event e JOIN prospect_sequence s "
        "ON s.id=e.sequence_id WHERE s.mailbox_id=? AND e.id>? ORDER BY e.id LIMIT 200",
        (mailbox_id, after),
    ).fetchall()
    items = [{**dict(r), "detail": json.loads(r["detail"])} for r in rows]
    return {"events": items, "next_cursor": items[-1]["id"] if items else after}


def listing(conn, mailbox_id):
    rows = conn.execute(
        "SELECT * FROM prospect_sequence WHERE mailbox_id=? ORDER BY created_at DESC", (mailbox_id,)
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        assignment = conn.execute(
            "SELECT owner,pending,version FROM prospect_assignment WHERE sequence_id=?",
            (row["id"],),
        ).fetchone()
        item["assignment"] = dict(assignment) if assignment else None
        item["payload"] = json.loads(item["payload"])
        item["steps"] = [
            dict(s)
            for s in conn.execute(
                "SELECT day,subject,body,state,sent_at FROM prospect_step WHERE sequence_id=? "
                "ORDER BY day",
                (row["id"],),
            )
        ]
        result.append(item)
    return result
