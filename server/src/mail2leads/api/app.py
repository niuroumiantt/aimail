"""只读 API + 托管前端。人的两个动作(确认线索、发送)在 M4/M5 加进来。

JSON 形状与 web/src/data/types.ts 一致:界面不知道也不该知道数据库长什么样。
"""

from __future__ import annotations

import csv
import io
import json
import secrets
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from mail2leads import send as send_mod
from mail2leads.ingest import attachments
from mail2leads.store import history, leads, outbox, repo
from mail2leads.tasks import draft as draft_mod


def who(request: Request) -> str:
    """人的身份。经 tailscale serve 进来时带 Tailscale-User-Login;否则界面自己带 X-User。"""
    return (
        request.headers.get("tailscale-user-login") or request.headers.get("x-user") or ""
    ).strip()


def machine(request: Request, tokens: dict[str, str]) -> str:
    """机器的身份:Authorization: Bearer <令牌>。机器不是人:它只能读 /v1,写线索的接口不认它。"""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return ""
    given = auth[7:].strip()
    for name, value in tokens.items():
        if secrets.compare_digest(value, given):
            return name
    return ""


CSV_COLUMNS = (
    "id",
    "status",
    "company",
    "contact",
    "email",
    "wants",
    "quantity",
    "region",
    "next_step",
    "confirmed_by",
    "confirmed_at",
    "updated_at",
    "thread_id",
    "subject",
)


def leads_csv(items: list[dict]) -> str:
    """一行一条线索,Excel 直接开(带 BOM)。"""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for lead in items:
        flat = {
            **lead,
            "thread_id": lead["source"]["thread_id"],
            "subject": lead["source"]["subject"],
        }
        writer.writerow([flat.get(c, "") for c in CSV_COLUMNS])
    return "\ufeff" + buf.getvalue()


def _suggestion_out(row: sqlite3.Row) -> dict:
    p = json.loads(row["payload"])
    return {
        "id": str(row["id"]),
        "thread_id": str(row["thread_id"]),
        "company": p.get("company", ""),
        "contact": p.get("contact", ""),
        "wants": p.get("wants", ""),
        "quantity": p.get("quantity", ""),
        "region": p.get("region", ""),
        "priority": p.get("priority", "normal"),
        "unverified": p.get("unverified", []),
        "model": row["model"],
        "task_version": row["task_version"],
        "produced_at": row["produced_at"],
    }


def _lead_out(row: sqlite3.Row) -> dict:
    return {
        "id": str(row["id"]),
        "thread_id": str(row["thread_id"]),
        "company": row["company"],
        "contact": row["contact"],
        "wants": row["wants"],
        "quantity": row["quantity"],
        "region": row["region"],
        "status": row["status"],
        "confirmed_by": row["confirmed_by"],
        "confirmed_at": row["confirmed_at"],
        "next_step": row["next_step"],
    }


class Decision(BaseModel):
    overrides: dict[str, str] | None = None


class LeadPatch(BaseModel):
    status: str | None = None
    next_step: str | None = None


class SendBody(BaseModel):
    token: str
    to: list[str]
    subject: str
    body: str
    draft_id: str | None = None


def _draft_out(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    base = {
        "id": str(row["id"]),
        "model": row["model"],
        "task_version": row["task_version"],
        "produced_at": row["produced_at"],
        "status": row["status"],
    }
    if row["status"] == "failed":
        return {**base, "reason": row["reason"]}
    return {**base, **json.loads(row["payload"])}


def _company_of(email_addr: str) -> str:
    """M4 之前没有模型提取,公司先用邮箱域名顶着——诚实的占位,不是编的。"""
    domain = email_addr.split("@")[-1]
    return domain.split(".")[0] if domain else ""


def _reading_out(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    base = {
        "model": row["model"],
        "task_version": row["task_version"],
        "produced_at": row["produced_at"],
        "status": row["status"],
    }
    if row["status"] == "failed":
        return {**base, "reason": row["reason"]}
    return {**base, **json.loads(row["payload"])}


def _attachments_out(conn: sqlite3.Connection, message_pk: int) -> list[dict] | None:
    items = attachments.texts_for_message(conn, message_pk)
    if not items:
        return None
    return [
        {
            "id": str(a.attachment_id),
            "name": a.filename,
            "size": a.size,
            "read": a.status,
            "reason": a.reason,
        }
        for a in items
    ]


def _thread_out(conn: sqlite3.Connection, row: sqlite3.Row, with_messages: bool) -> dict:
    messages = repo.thread_messages(conn, int(row["id"]))
    last_in = next((m for m in reversed(messages) if m["direction"] == "in"), None)
    reading = _reading_out(repo.latest_reading(conn, int(last_in["id"]))) if last_in else None
    out = {
        "id": str(row["id"]),
        "subject": row["subject"],
        "company": _company_of(row["contact_email"]),
        "contact": row["contact_name"] or row["contact_email"],
        "email": row["contact_email"],
        "region": "",
        "scale": f"{len(messages)} 封",
        "folder": row["folder"],
        "updated_at": row["last_at"],
        "reading": reading,
        "messages": [],
    }
    if with_messages:
        out["history"] = [
            {
                "id": str(h.thread_id),
                "subject": h.subject,
                "first_at": h.first_at,
                "last_at": h.last_at,
                "folder": h.folder,
                "replied": h.replied,
                "lead_status": h.lead_status,
                "excerpt": h.excerpt,
            }
            for h in history.related_threads(conn, int(row["mailbox_id"]), int(row["id"]))
        ]
        out["messages"] = [
            {
                "id": str(m["id"]),
                "direction": m["direction"],
                "from_name": m["from_name"] or m["from_email"],
                "from_email": m["from_email"],
                "sent_at": m["sent_at"],
                "body": m["body_new"],
                "quoted": m["body_quoted"] or None,
                "attachments": _attachments_out(conn, int(m["id"])),
            }
            for m in messages
        ]
    return out


def create_app(
    conn: sqlite3.Connection,
    mailbox_id: int,
    web_dist: Path | None = None,
    *,
    sender: str = "",
    sender_name: str = "",
    transport: send_mod.Transport | None = None,
    api_tokens: dict[str, str] | None = None,
    webhook_configured: bool = False,
) -> FastAPI:
    app = FastAPI(title="mail2leads")
    tokens = send_mod.TokenBox()

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/api/threads")
    def threads(folder: str | None = None) -> list[dict]:
        return [
            _thread_out(conn, row, with_messages=False)
            for row in repo.list_threads(conn, mailbox_id, folder)
        ]

    @app.get("/api/threads/{thread_id}")
    def thread(thread_id: int) -> dict:
        row = repo.get_thread(conn, thread_id)
        if row is None or int(row["mailbox_id"]) != mailbox_id:
            raise HTTPException(404, "没有这条线程")
        return _thread_out(conn, row, with_messages=True)

    @app.get("/api/attachments/{attachment_id}/text")
    def attachment_text(attachment_id: int) -> dict:
        item = attachments.get_text(conn, mailbox_id, attachment_id)
        if item is None:
            raise HTTPException(404, "没有这个附件")
        return {
            "id": str(item.attachment_id),
            "name": item.filename,
            "status": item.status,
            "text": item.text,
            "reason": item.reason,
        }

    def _machine(request: Request) -> str:
        name = machine(request, api_tokens or {})
        if not name:
            raise HTTPException(401, "需要 API 令牌:Authorization: Bearer <令牌>")
        return name

    @app.get("/v1/leads")
    def v1_leads(
        request: Request,
        since: str = "",
        after: int = 0,
        status: str | None = None,
        limit: int = 200,
    ) -> dict:
        """给下游拉的线索:只有人确认过的事实,按 (updated_at, id) 升序;
        下一页把 next_since / next_after 原样传回来。"""
        _machine(request)
        if status is not None and status not in leads.LEAD_STATUSES:
            raise HTTPException(422, f"状态只能是 {leads.LEAD_STATUSES}")
        rows = leads.since_leads(conn, mailbox_id, since, after, status, max(1, min(limit, 1000)))
        items = [leads.lead_v1(conn, r) for r in rows]
        return {
            "version": "v1",
            "leads": items,
            "next_since": items[-1]["updated_at"] if items else since,
            "next_after": int(items[-1]["id"]) if items else after,
        }

    def _csv_response() -> Response:
        items = [leads.lead_v1(conn, r) for r in leads.list_leads(conn, mailbox_id)]
        return Response(
            leads_csv(items),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="leads.csv"'},
        )

    @app.get("/v1/leads.csv")
    def v1_leads_csv(request: Request) -> Response:
        _machine(request)
        return _csv_response()

    @app.get("/api/leads.csv")
    def api_leads_csv() -> Response:
        return _csv_response()

    @app.get("/api/outbox")
    def api_outbox() -> dict:
        """推送送到没有。没配 webhook 就是 configured=false,界面什么都不显示。"""
        return {"configured": webhook_configured, **outbox.status(conn, mailbox_id)}

    @app.get("/api/leads/suggestions")
    def suggestions() -> list[dict]:
        return [_suggestion_out(r) for r in leads.open_suggestions(conn, mailbox_id)]

    @app.get("/api/leads/failed")
    def failed() -> dict:
        return {"count": leads.failed_suggestions(conn, mailbox_id)}

    @app.get("/api/leads")
    def lead_list() -> list[dict]:
        return [_lead_out(r) for r in leads.list_leads(conn, mailbox_id)]

    def _person(request: Request) -> str:
        user = who(request)
        if not user:
            raise HTTPException(401, "确认线索要先写上你的名字")
        return user

    @app.post("/api/leads/suggestions/{suggestion_id}/confirm")
    def confirm(suggestion_id: int, request: Request, decision: Decision | None = None) -> dict:
        try:
            lead_id = leads.confirm(
                conn, suggestion_id, _person(request), (decision or Decision()).overrides
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        row = conn.execute("SELECT * FROM lead WHERE id = ?", (lead_id,)).fetchone()
        return _lead_out(row)

    @app.post("/api/leads/suggestions/{suggestion_id}/dismiss")
    def dismiss(suggestion_id: int, request: Request) -> dict:
        try:
            leads.dismiss(conn, suggestion_id, _person(request))
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"ok": True}

    @app.get("/api/threads/{thread_id}/draft")
    def get_draft(thread_id: int) -> dict:
        return {"draft": _draft_out(draft_mod.latest_draft(conn, thread_id))}

    @app.post("/api/threads/{thread_id}/draft")
    def make_draft(thread_id: int, request: Request) -> dict:
        _person(request)
        if repo.get_thread(conn, thread_id) is None:
            raise HTTPException(404, "没有这条线程")
        draft_id = draft_mod.make_draft(conn, thread_id)
        row = conn.execute("SELECT * FROM reply_draft WHERE id = ?", (draft_id,)).fetchone()
        return {"draft": _draft_out(row)}

    @app.post("/api/threads/{thread_id}/send-token")
    def send_token(thread_id: int, request: Request) -> dict:
        """一次性令牌:只签给人,绑定线程,十分钟有效。后台任务没有请求,也就没有令牌。"""
        if repo.get_thread(conn, thread_id) is None:
            raise HTTPException(404, "没有这条线程")
        token = tokens.mint(thread_id, _person(request))
        return {"token": token.value, "expires_in": send_mod.TOKEN_TTL_SECONDS}

    @app.post("/api/threads/{thread_id}/send")
    def send(thread_id: int, request: Request, payload: SendBody) -> dict:
        user = _person(request)
        if transport is None or not sender:
            raise HTTPException(503, "没有配置 SMTP,发不了")
        try:
            token = tokens.consume(payload.token, thread_id, user)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        try:
            send_mod.send(
                conn,
                token=token,
                mailbox_id=mailbox_id,
                sender=sender,
                sender_name=sender_name,
                thread_id=thread_id,
                to=payload.to,
                subject=payload.subject,
                body=payload.body,
                transport=transport,
                draft_id=int(payload.draft_id) if payload.draft_id else None,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        row = repo.get_thread(conn, thread_id)
        assert row is not None
        return _thread_out(conn, row, with_messages=True)

    @app.patch("/api/leads/{lead_id}")
    def patch_lead(lead_id: int, request: Request, patch: LeadPatch) -> dict:
        try:
            leads.update_lead(conn, lead_id, _person(request), patch.status, patch.next_step)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        row = conn.execute("SELECT * FROM lead WHERE id = ?", (lead_id,)).fetchone()
        return _lead_out(row)

    if web_dist and (web_dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str) -> FileResponse:
            # history 路由:所有非 API 路径都回 index.html,前端自己认路
            return FileResponse(web_dist / "index.html")

    return app
