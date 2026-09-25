"""Human reconciliation for uncertain SMTP outcomes; never calls a transport."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta

from aimail.ingest.parse import parse
from aimail.ingest.run import store_raw
from aimail.store import repo

SENDING_GRACE = timedelta(minutes=10)


def _check_owner(conn: sqlite3.Connection, thread_id: int, actor: str, original_actor: str) -> None:
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='followup'"
    ).fetchone()
    state = (
        conn.execute("SELECT owner FROM followup WHERE thread_id=?", (thread_id,)).fetchone()
        if table
        else None
    )
    owner = state["owner"] if state else original_actor
    if owner != actor:
        raise PermissionError("只有当前负责人可以核对该发送")


def resolve(
    conn: sqlite3.Connection,
    *,
    thread_id: int,
    attempt_id: int,
    actor: str,
    outcome: str,
    evidence_reference: str,
    now: datetime | None = None,
) -> dict:
    """Close an uncertain attempt only after an owner records provider evidence."""
    if outcome not in {"sent", "not_sent"}:
        raise ValueError("核对结果必须是 sent 或 not_sent")
    evidence_reference = " ".join(evidence_reference.split())
    if len(evidence_reference) < 6 or len(evidence_reference) > 500:
        raise ValueError("请填写至少 6 个字符的服务商记录编号或核对依据")

    now = now or datetime.now(UTC)
    attempt = conn.execute(
        "SELECT r.*,t.mailbox_id,t.contact_email FROM reply_attempt r "
        "JOIN thread t ON t.id=r.thread_id WHERE r.id=? AND r.thread_id=?",
        (attempt_id, thread_id),
    ).fetchone()
    if not attempt:
        raise LookupError("没有这条待核对发送")
    _check_owner(conn, thread_id, actor, attempt["actor"])

    prior = conn.execute(
        "SELECT actor,outcome,evidence_reference FROM reply_resolution WHERE attempt_id=?",
        (attempt_id,),
    ).fetchone()
    if prior:
        if (
            prior["actor"] == actor
            and prior["outcome"] == outcome
            and prior["evidence_reference"] == evidence_reference
        ):
            return {"ok": True, "already_resolved": True, "outcome": outcome}
        raise ValueError("该发送已经核对，不能覆盖审计记录")

    if attempt["state"] not in {"sending", "unknown"}:
        raise LookupError("没有可核对的发送")
    created = datetime.fromisoformat(attempt["created_at"].replace("Z", "+00:00"))
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    if attempt["state"] == "sending" and now - created < SENDING_GRACE:
        raise ValueError("发送任务可能仍在运行；请等待 10 分钟后再核对")

    message_pk = None
    if outcome == "sent":
        raw = bytes(attempt["raw"])
        try:
            parsed = parse(raw)
        except Exception as exc:
            raise ValueError("待核对原邮件无法解析，记录保持锁定") from exc
        if parsed.from_email.casefold() != attempt["sender"].strip().casefold():
            raise ValueError("待核对邮件发件身份与记录不匹配")
        if attempt["contact_email"].casefold() not in {
            address.casefold() for address in parsed.to_emails
        }:
            raise ValueError("待核对邮件收件人与当前会话不匹配")
        if (
            not parsed.in_reply_to
            or repo.thread_of_message_id(conn, attempt["mailbox_id"], parsed.in_reply_to)
            != thread_id
        ):
            raise ValueError("待核对邮件未引用当前会话，记录保持锁定")

        digest = hashlib.sha256(raw).hexdigest()
        existing_message = conn.execute(
            "SELECT id,thread_id,direction FROM message WHERE raw_sha256=?", (digest,)
        ).fetchone()
        if existing_message:
            if existing_message["thread_id"] != thread_id or existing_message["direction"] != "out":
                raise ValueError("同一原文已关联到其他会话，记录保持锁定")
            message_pk = int(existing_message["id"])
        else:
            message_pk, _ = store_raw(
                conn,
                attempt["mailbox_id"],
                raw,
                "out",
                now,
                target_thread_id=thread_id,
            )
            if message_pk is None:
                existing_message = conn.execute(
                    "SELECT id,thread_id,direction FROM message WHERE raw_sha256=?", (digest,)
                ).fetchone()
                if (
                    not existing_message
                    or existing_message["thread_id"] != thread_id
                    or existing_message["direction"] != "out"
                ):
                    raise ValueError("待核对邮件已存在但关联不一致，记录保持锁定")
                message_pk = int(existing_message["id"])

    conn.execute("BEGIN IMMEDIATE")
    try:
        prior = conn.execute(
            "SELECT actor,outcome,evidence_reference FROM reply_resolution WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        if prior:
            if (
                prior["actor"] == actor
                and prior["outcome"] == outcome
                and prior["evidence_reference"] == evidence_reference
            ):
                conn.commit()
                return {"ok": True, "already_resolved": True, "outcome": outcome}
            raise ValueError("该发送已经核对，不能覆盖审计记录")
        current = conn.execute(
            "SELECT state,actor FROM reply_attempt WHERE id=? AND thread_id=?",
            (attempt_id, thread_id),
        ).fetchone()
        if not current or current["state"] not in {"sending", "unknown"}:
            raise ValueError("该发送状态已变化，请刷新后核对")
        _check_owner(conn, thread_id, actor, current["actor"])
        resolution_state = "recorded" if outcome == "sent" else "resolved_not_sent"
        updated = conn.execute(
            "UPDATE reply_attempt SET state=? WHERE id=? AND state IN ('sending','unknown')",
            (resolution_state, attempt_id),
        )
        if updated.rowcount != 1:
            raise ValueError("该发送状态已变化，请刷新后核对")
        conn.execute(
            "INSERT INTO reply_resolution(attempt_id,thread_id,actor,outcome,evidence_reference,"
            "message_pk,resolved_at) VALUES(?,?,?,?,?,?,?)",
            (
                attempt_id,
                thread_id,
                actor,
                outcome,
                evidence_reference,
                message_pk,
                now.isoformat(),
            ),
        )
        if outcome == "sent":
            conn.execute("UPDATE thread SET folder='replied' WHERE id=?", (thread_id,))
            if not conn.execute(
                "SELECT 1 FROM outbound WHERE message_pk=?", (message_pk,)
            ).fetchone():
                conn.execute(
                    "INSERT INTO outbound(mailbox_id,thread_id,message_pk,draft_id,sent_by,sent_at,"
                    "transport_result) VALUES(?,?,?,?,?,?,?)",
                    (
                        attempt["mailbox_id"],
                        thread_id,
                        message_pk,
                        None,
                        attempt["actor"],
                        attempt["created_at"],
                        "manually_confirmed_by_provider_evidence",
                    ),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"ok": True, "already_resolved": False, "outcome": outcome}
