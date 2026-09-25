"""发信。系统里唯一能把内容发到外部的地方,而且只认一次性令牌(宪法第二条)。

令牌由 API 层在人的请求里签发,绑定线程与人,十分钟有效,用一次作废。
后台任务(收信、读数、起草)拿不到令牌——它们连这个模块都不 import,有测试守着。
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import ssl
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime
from typing import Protocol

from aimail.ingest.run import store_raw

TOKEN_TTL_SECONDS = 600


def validate_sender(sender: str) -> None:
    """The company public sales address is receive-only, on every send path."""
    if sender.strip().casefold() == "sales@glocalstorage.com":
        raise PermissionError("sales@glocalstorage.com 只收信，请使用个人邮箱发送")


@dataclass(frozen=True)
class SendToken:
    value: str
    thread_id: int
    user: str
    expires_at: float


class TokenBox:
    """内存里的一次性令牌。进程重启即失效,这正是我们要的。"""

    def __init__(self) -> None:
        self._tokens: dict[str, SendToken] = {}
        self._lock = threading.Lock()

    def mint(self, thread_id: int, user: str, now: float | None = None) -> SendToken:
        user = user.strip()
        if not user:
            raise PermissionError("发信令牌只签给人")
        now = time.time() if now is None else now
        token = SendToken(secrets.token_urlsafe(24), thread_id, user, now + TOKEN_TTL_SECONDS)
        with self._lock:
            self._tokens[token.value] = token
        return token

    def consume(self, value: str, thread_id: int, user: str, now: float | None = None) -> SendToken:
        """验令牌并作废。不匹配、过期、用过,都抛 PermissionError。"""
        now = time.time() if now is None else now
        with self._lock:
            token = self._tokens.pop(value, None)
        if token is None:
            raise PermissionError("令牌无效或已用过")
        if token.thread_id != thread_id or token.user != user.strip():
            raise PermissionError("令牌不是签给这个线程或这个人的")
        if now > token.expires_at:
            raise PermissionError("令牌过期,重新点发送")
        return token


class Transport(Protocol):
    def deliver(self, sender: str, recipients: list[str], raw: bytes) -> str: ...


class SmtpTransport:
    """真 SMTP。465 走 SMTP_SSL,其余端口 STARTTLS;都用 ssl.create_default_context()。"""

    def __init__(self, host: str, port: int, user: str, password: str) -> None:
        self.host, self.port, self.user, self.password = host, port, user, password

    def deliver(self, sender: str, recipients: list[str], raw: bytes) -> str:
        import smtplib

        validate_sender(sender)
        if not all((self.host, self.user, self.password)):
            raise PermissionError("发信需要明确配置个人邮箱 SMTP")
        if sender.strip().casefold() != self.user.strip().casefold():
            raise PermissionError("发件地址与 SMTP 账号不一致")
        context = ssl.create_default_context()
        if self.port == 465:
            server = smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=30)
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=30)
            server.starttls(context=context)
        with server:
            server.login(self.user, self.password)
            refused = server.sendmail(sender, recipients, raw)
        return "ok" if not refused else f"部分拒收:{refused}"


def build_message(
    *,
    sender: str,
    sender_name: str,
    to: list[str],
    subject: str,
    body: str,
    in_reply_to: str,
    references: str,
    now: datetime,
) -> tuple[EmailMessage, str]:
    validate_sender(sender)
    msg = EmailMessage()
    domain = sender.split("@")[-1] or "aimail.local"
    message_id = f"<{uuid.uuid4()}@{domain}>"
    msg["Message-ID"] = message_id
    msg["From"] = f"{sender_name} <{sender}>" if sender_name else sender
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg["Date"] = format_datetime(now)
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = f"{references} {in_reply_to}".strip() if references else in_reply_to
    msg.set_content(body)
    return msg, message_id


def send(
    conn: sqlite3.Connection,
    *,
    token: SendToken,
    mailbox_id: int,
    sender: str,
    sender_name: str,
    thread_id: int,
    to: list[str],
    subject: str,
    body: str,
    transport: Transport,
    draft_id: int | None = None,
    now: datetime | None = None,
) -> int:
    """发一封。要求一个已经验过的 SendToken——没有令牌这个函数根本调不动。"""
    if not isinstance(token, SendToken) or token.thread_id != thread_id:
        raise PermissionError("没有有效的发信令牌")
    if not to or not body.strip():
        raise ValueError("收件人和正文不能为空")
    now = now or datetime.now(UTC)
    last = conn.execute(
        "SELECT message_id, refs FROM message WHERE thread_id = ? AND direction = 'in' "
        "ORDER BY sent_at DESC, id DESC LIMIT 1",
        (thread_id,),
    ).fetchone()
    msg, _ = build_message(
        sender=sender,
        sender_name=sender_name,
        to=to,
        subject=subject,
        body=body,
        in_reply_to=last["message_id"] if last else "",
        references=last["refs"] if last else "",
        now=now,
    )
    raw = msg.as_bytes()
    if conn.in_transaction:
        raise ValueError("发信前必须先提交业务事务")
    try:
        attempt = conn.execute(
            "INSERT INTO reply_attempt(thread_id,token_hash,sender,actor,raw,state,created_at) "
            "VALUES(?,?,?,?,?,'sending',?)",
            (
                thread_id,
                hashlib.sha256(token.value.encode()).hexdigest(),
                sender,
                token.user,
                raw,
                now.isoformat(),
            ),
        ).lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError("该会话有待核对的发送记录或令牌已用过，请勿重复发送") from None
    try:
        result = transport.deliver(sender, to, raw)
        if result != "ok":
            raise ValueError("transport not fully accepted")
    except Exception:
        conn.execute("UPDATE reply_attempt SET state='unknown' WHERE id=?", (attempt,))
        conn.commit()
        raise ValueError("发送结果待核对，请检查已发送邮件，禁止自动重试") from None
    pk, _ = store_raw(conn, mailbox_id, raw, "out", now)
    if pk is None:
        raise RuntimeError("发出去的信没能落库(重复的 Message-ID?)")
    conn.execute("UPDATE thread SET folder = 'replied' WHERE id = ?", (thread_id,))
    cur = conn.execute(
        "INSERT INTO outbound (mailbox_id, thread_id, message_pk, draft_id, sent_by, sent_at, "
        "transport_result) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            mailbox_id,
            thread_id,
            pk,
            draft_id,
            token.user,
            now.replace(microsecond=0).isoformat(),
            result,
        ),
    )
    conn.execute("UPDATE reply_attempt SET state='recorded' WHERE id=?", (attempt,))
    conn.commit()
    return int(cur.lastrowid)
