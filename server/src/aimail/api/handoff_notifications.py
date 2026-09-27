"""Internal employee notifications, separate from customer outreach and replies."""

import hashlib
import html
import secrets
from datetime import UTC, datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import format_datetime
from urllib.parse import urlencode

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from aimail.send import validate_sender


class Notice(BaseModel):
    account_id: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)
    actor: str = Field(min_length=3, max_length=254)
    recipient: str = Field(min_length=3, max_length=254)
    subject: str = Field(min_length=1, max_length=200, pattern=r"^[^\r\n]+$")
    summary: str = Field(max_length=4000)
    thread_id: int | None = Field(default=None, ge=1)


def install(app, conn, *, token, members, admins, accounts, shared_mailbox_id):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS handoff_notice ("
        "id TEXT PRIMARY KEY, digest TEXT NOT NULL, state TEXT NOT NULL, "
        "message_id TEXT NOT NULL, created_at TEXT NOT NULL)"
    )

    @app.post("/v1/handoff-notifications")
    def notify(request: Request, body: Notice):
        if not token or not secrets.compare_digest(
            request.headers.get("authorization", ""), "Bearer " + token
        ):
            raise HTTPException(401, "需要集成令牌")
        actor, recipient = body.actor.casefold().strip(), body.recipient.casefold().strip()
        if actor not in admins or recipient not in members or actor == recipient:
            raise HTTPException(403, "仅允许管理员向已登记员工发送交接通知")
        key = f"{body.account_id}:{body.version}"
        digest = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
        previous = conn.execute("SELECT * FROM handoff_notice WHERE id=?", (key,)).fetchone()
        if previous:
            if previous["digest"] != digest:
                raise HTTPException(409, "同一交接版本的通知内容已改变")
            return {
                "id": key,
                "state": "unknown" if previous["state"] == "sending" else previous["state"],
            }
        account = accounts.get(actor)
        if not account or not account.transport or account.address.casefold() != actor:
            raise HTTPException(503, "管理员个人发件账号尚未配置")
        validate_sender(account.address)
        originals = []
        if body.thread_id:
            if not conn.execute(
                "SELECT id FROM thread WHERE id=? AND mailbox_id=?",
                (body.thread_id, shared_mailbox_id),
            ).fetchone():
                raise HTTPException(404, "共享邮箱线程不存在")
            rows = conn.execute(
                "SELECT id,raw FROM message WHERE thread_id=? ORDER BY id", (body.thread_id,)
            ).fetchall()
            if sum(len(row["raw"]) for row in rows) > 20 * 1024 * 1024:
                raise HTTPException(413, "原邮件附件超过通知上限，请先处理附件大小")
            originals = [(row["id"], bytes(row["raw"])) for row in rows]
        message = EmailMessage(policy=policy.SMTP)
        message["Date"] = format_datetime(datetime.now(UTC))
        message["From"], message["To"] = account.address, recipient
        message["Subject"] = "[待接手线索] " + body.subject
        message_id = "<handoff-" + hashlib.sha256(key.encode()).hexdigest() + "@glocalstorage.cn>"
        message["Message-ID"] = message_id
        base = "https://leads.glocalstorage.cn/?" + urlencode({"lead": body.account_id})
        message.set_content(
            f"{actor} 分配了线索给你。\n\n{body.summary}\n\n接受或退回：{base}\n"
            "需登录本人账号并确认；打开邮件不会自动接手。"
        )
        buttons = "".join(
            '<a style="display:inline-block;padding:12px 24px;margin-right:12px;'
            'background:#245b4d;color:white;text-decoration:none;border-radius:6px" '
            f'href="{html.escape(base + "&decision=" + action, quote=True)}">{label}</a>'
            for action, label in [("accept", "接受"), ("decline", "退回")]
        )
        attachment_hint = "原邮件见附件。" if originals else "客户资料可在上述线索页面查看。"
        message.add_alternative(
            f"<html><body><p>{buttons}</p><h2>线索交接</h2><p>{html.escape(actor)} 分配给你</p>"
            f'<p style="white-space:pre-wrap">{html.escape(body.summary)}</p>'
            f"<p>请登录后确认接受或填写退回原因。{attachment_hint}</p></body></html>",
            subtype="html",
        )
        for mid, raw in originals:
            original = BytesParser(policy=policy.default).parsebytes(raw)
            message.add_attachment(original, filename=f"original-{mid}.eml")
        conn.execute(
            "INSERT INTO handoff_notice VALUES(?,?,?,?,?)",
            (key, digest, "sending", message_id, datetime.now(UTC).isoformat()),
        )
        conn.commit()  # Record before SMTP; ambiguous results must never auto-resend.
        try:
            result = account.transport.deliver(account.address, [recipient], message.as_bytes())
            state = "sent" if result == "ok" else "unknown"
        except Exception:
            state = "unknown"
        conn.execute("UPDATE handoff_notice SET state=? WHERE id=?", (state, key))
        conn.commit()
        return {"id": key, "state": state}
