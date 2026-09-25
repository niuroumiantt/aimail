"""只读 API + 托管前端。人的两个动作(确认线索、发送)在 M4/M5 加进来。

JSON 形状与 web/src/data/types.ts 一致:界面不知道也不该知道数据库长什么样。
"""

from __future__ import annotations

import csv
import io
import json
import secrets
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import anyio
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from mail2leads import backends
from mail2leads import send as send_mod
from mail2leads.config import DEFAULT_TASKS
from mail2leads.ingest import attachments
from mail2leads.send.accounts import SendingAccount
from mail2leads.store import assistant, followup, history, leads, outbox, repo
from mail2leads.tasks import ask_mailbox
from mail2leads.tasks import draft as draft_mod
from mail2leads.tasks.read import read_message


def who(request: Request, require_oa_auth: bool = False) -> str:
    """人的身份。经 tailscale serve 进来时带 Tailscale-User-Login;否则界面自己带 X-User。"""
    if require_oa_auth:
        return request.headers.get("x-oa-user", "").strip()
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


class AssistantQuestion(BaseModel):
    question: str


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
    tasks: frozenset[str] = DEFAULT_TASKS,
    display_name: str = "",
    sync_mailbox: Callable[[], None] | None = None,
    require_oa_auth: bool = False,
    outreach_import_token: str = "",
    outreach_enabled: bool = False,
    outreach_approval_proxy_key: str = "",
    mailbox_access: dict[str, tuple[str, ...]] | None = None,
    mailbox_tasks: dict[str, frozenset[str]] | None = None,
    sync_mailboxes: dict[str, Callable[[], None]] | None = None,
    followup_members: tuple[str, ...] = (),
    sending_accounts: dict[str, SendingAccount] | None = None,
) -> FastAPI:
    app = FastAPI(title="mail2leads")
    followup.init(conn)
    tokens = send_mod.TokenBox()
    # create_app receives one SQLite connection for the process. FastAPI executes sync
    # endpoints in a thread pool, so a browser's parallel initial requests can otherwise
    # use that connection concurrently and trigger sqlite3.InterfaceError. Serialize only
    # data APIs; static assets and the SPA shell remain concurrent.
    api_connection_lock = threading.Lock()

    @app.middleware("http")
    async def serialize_shared_sqlite(request: Request, call_next):
        if request.url.path.startswith(("/api/", "/v1/")):
            await anyio.to_thread.run_sync(api_connection_lock.acquire)
            try:
                return await call_next(request)
            finally:
                api_connection_lock.release()
        return await call_next(request)

    def _mailbox_row(request: Request) -> sqlite3.Row:
        default = conn.execute("SELECT * FROM mailbox WHERE id = ?", (mailbox_id,)).fetchone()
        if default is None:
            raise HTTPException(503, "邮箱尚未配置")
        if not require_oa_auth:
            return default
        identity = request.headers.get("x-oa-email", "").strip().lower()
        if not identity:
            raise HTTPException(401, "登录身份没有邮箱地址")
        allowed = (mailbox_access or {}).get(identity, (identity,))
        rows = {
            row["address"].lower(): row
            for row in conn.execute("SELECT * FROM mailbox").fetchall()
            if row["address"].lower() in {address.lower() for address in allowed}
        }
        if not rows:
            raise HTTPException(403, "当前账号没有可访问的邮箱")
        requested = request.headers.get("x-mailbox-address", "").strip().lower()
        if requested:
            if requested not in rows:
                raise HTTPException(403, "不能访问这个邮箱")
            return rows[requested]
        for address in allowed:
            if address.lower() in rows:
                return rows[address.lower()]
        return next(iter(rows.values()))

    def _mailbox_tasks(address: str) -> frozenset[str]:
        return (mailbox_tasks or {}).get(address.lower(), tasks)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/api/mailboxes")
    def api_mailboxes(request: Request) -> dict:
        current = _mailbox_row(request)
        if not require_oa_auth:
            rows = [current]
        else:
            identity = request.headers.get("x-oa-email", "").strip().lower()
            allowed = (mailbox_access or {}).get(identity, (identity,))
            by_address = {
                row["address"].lower(): row
                for row in conn.execute("SELECT * FROM mailbox").fetchall()
            }
            rows = [by_address[a.lower()] for a in allowed if a.lower() in by_address]
        return {
            "default": current["address"],
            "items": [
                {
                    "address": row["address"],
                    "display_name": row["display_name"],
                    "tasks": sorted(_mailbox_tasks(row["address"])),
                }
                for row in rows
            ],
        }

    @app.post("/api/sync")
    def sync(request: Request) -> dict:
        """立即同步一次；调用方等待完成，成功后便可直接刷新列表。"""
        selected = _mailbox_row(request)
        syncer = (sync_mailboxes or {}).get(selected["address"].lower())
        if syncer is None and int(selected["id"]) == mailbox_id:
            syncer = sync_mailbox
        if syncer is None:
            raise HTTPException(503, "当前服务没有配置收信")
        try:
            syncer()
        except Exception as exc:  # noqa: BLE001 - 把同步失败明确交给界面
            raise HTTPException(502, f"收信失败：{exc}") from exc
        return {"ok": True}

    @app.get("/api/mailbox")
    def api_mailbox(request: Request) -> dict:
        """这个服务伺候哪个邮箱、开了哪些任务。界面据此显示地址、藏起没开的入口。"""
        m = _mailbox_row(request)
        return {
            "address": m["address"],
            "display_name": display_name if int(m["id"]) == mailbox_id else m["display_name"],
            "tasks": sorted(_mailbox_tasks(m["address"])),
        }

    @app.get("/api/threads")
    def threads(request: Request, folder: str | None = None) -> list[dict]:
        selected = _mailbox_row(request)
        return [
            _thread_out(conn, row, with_messages=False)
            for row in repo.list_threads(conn, int(selected["id"]), folder)
        ]

    @app.get("/api/threads/{thread_id}")
    def thread(thread_id: int, request: Request) -> dict:
        selected = _mailbox_row(request)
        row = repo.get_thread(conn, thread_id, int(selected["id"]))
        if row is None:
            raise HTTPException(404, "没有这条线程")
        return _thread_out(conn, row, with_messages=True)

    @app.post("/api/threads/{thread_id}/analyze")
    def analyze_thread(thread_id: int, request: Request) -> dict:
        selected = _mailbox_row(request)
        row = repo.get_thread(conn, thread_id, int(selected["id"]))
        if row is None:
            raise HTTPException(404, "没有这条线程")
        ready, reason = backends.ready()
        if not ready:
            raise HTTPException(503, f"AI 尚未配置：{reason}")
        messages = repo.thread_messages(conn, thread_id)
        source = next((item for item in reversed(messages) if item["direction"] == "in"), None)
        if source is None:
            raise HTTPException(422, "这个话题没有可分析的来信")
        read_message(conn, int(source["id"]), tasks=_mailbox_tasks(selected["address"]))
        refreshed = repo.get_thread(conn, thread_id, int(selected["id"]))
        assert refreshed is not None
        return _thread_out(conn, refreshed, with_messages=True)

    def _assistant_status(selected: sqlite3.Row) -> dict:
        ready, reason = backends.ready()
        return {
            "configured": ready,
            "reason": reason,
            "model": backends.describe() if ready else "",
            "mailbox": selected["address"],
            "turns": assistant.conversation(conn, int(selected["id"])),
        }

    @app.get("/api/assistant")
    def assistant_history(request: Request) -> dict:
        return _assistant_status(_mailbox_row(request))

    @app.post("/api/assistant/clear")
    def assistant_clear(request: Request) -> dict:
        selected = _mailbox_row(request)
        actor = _person(request)
        assistant.append(conn, int(selected["id"]), "clear", "", actor, {"retained": True})
        return _assistant_status(selected)

    @app.post("/api/assistant")
    def assistant_ask(body: AssistantQuestion, request: Request) -> dict:
        selected = _mailbox_row(request)
        actor = _person(request)
        question = body.question.strip()
        if not question:
            raise HTTPException(422, "请输入问题")
        if len(question) > 2000:
            raise HTTPException(422, "问题不能超过 2000 字")
        ready, reason = backends.ready()
        if not ready:
            raise HTTPException(503, f"AI 尚未配置：{reason}")
        mailbox_id_for_assistant = int(selected["id"])
        previous = assistant.conversation(conn, mailbox_id_for_assistant)[-2:]
        history_payload = [
            {"question": item["question"], "findings": item.get("findings", [])}
            for item in previous
            if item["status"] == "done"
        ]
        rows = conn.execute(
            "SELECT id,thread_id,subject,from_email,sent_at,body_new FROM message "
            "WHERE mailbox_id=? ORDER BY sent_at DESC,id DESC",
            (mailbox_id_for_assistant,),
        ).fetchall()
        included = rows[:60]
        budget = min(3000, 48000 // max(len(included), 1))
        sources = [
            {
                "id": row["id"],
                "thread_id": row["thread_id"],
                "subject": row["subject"],
                "sent_at": row["sent_at"],
                "text": (row["subject"] + "\n" + row["from_email"] + "\n" + row["body_new"])[
                    :budget
                ],
            }
            for row in included
        ]
        truncated = sum(
            len(row["subject"] + row["from_email"] + row["body_new"]) + 2 > budget
            for row in included
        )
        turn_id = str(uuid4())
        assistant.append(
            conn,
            mailbox_id_for_assistant,
            "question",
            turn_id,
            actor,
            {"question": question, "actor": actor},
        )
        try:
            result = {
                "status": "done",
                "findings": ask_mailbox.ask(question, sources, history_payload),
                "model": backends.describe(),
                "task_version": ask_mailbox.TASK_VERSION,
                "produced_at": datetime.now(UTC).isoformat(),
                "scope": {
                    "total": len(rows),
                    "included": len(sources),
                    "truncated": truncated,
                    "attachments": False,
                },
            }
            assistant.append(conn, mailbox_id_for_assistant, "answer", turn_id, actor, result)
        except Exception as exc:
            assistant.append(
                conn,
                mailbox_id_for_assistant,
                "failure",
                turn_id,
                actor,
                {
                    "status": "failed",
                    "error": "分析失败或引用未通过核对，请重试。",
                    "error_type": type(exc).__name__,
                },
            )
            raise HTTPException(502, "分析失败或引用未通过核对，请重试。") from exc
        return _assistant_status(selected)

    @app.get("/api/attachments/{attachment_id}/text")
    def attachment_text(attachment_id: int, request: Request) -> dict:
        selected = _mailbox_row(request)
        item = attachments.get_text(conn, int(selected["id"]), attachment_id)
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
    def api_leads_csv(request: Request) -> Response:
        selected = _mailbox_row(request)
        items = [leads.lead_v1(conn, r) for r in leads.list_leads(conn, int(selected["id"]))]
        return Response(
            leads_csv(items),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="leads.csv"'},
        )

    @app.get("/api/outbox")
    def api_outbox(request: Request) -> dict:
        """推送送到没有。没配 webhook 就是 configured=false,界面什么都不显示。"""
        selected = _mailbox_row(request)
        return {"configured": webhook_configured, **outbox.status(conn, int(selected["id"]))}

    @app.get("/api/leads/suggestions")
    def suggestions(request: Request) -> list[dict]:
        selected = _mailbox_row(request)
        return [_suggestion_out(r) for r in leads.open_suggestions(conn, int(selected["id"]))]

    @app.get("/api/leads/failed")
    def failed(request: Request) -> dict:
        selected = _mailbox_row(request)
        return {"count": leads.failed_suggestions(conn, int(selected["id"]))}

    @app.get("/api/leads")
    def lead_list(request: Request) -> list[dict]:
        selected = _mailbox_row(request)
        return [_lead_out(r) for r in leads.list_leads(conn, int(selected["id"]))]

    def _person(request: Request) -> str:
        user = who(request, require_oa_auth)
        if not user:
            raise HTTPException(401, "确认线索要先写上你的名字")
        return user

    @app.post("/api/leads/suggestions/{suggestion_id}/confirm")
    def confirm(suggestion_id: int, request: Request, decision: Decision | None = None) -> dict:
        user = _person(request)
        selected = _mailbox_row(request)
        if not leads.suggestion_in(conn, suggestion_id, int(selected["id"])):
            raise HTTPException(404, "建议不存在或已处理")
        try:
            lead_id = leads.confirm(conn, suggestion_id, user, (decision or Decision()).overrides)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        row = conn.execute("SELECT * FROM lead WHERE id = ?", (lead_id,)).fetchone()
        return _lead_out(row)

    @app.post("/api/leads/suggestions/{suggestion_id}/dismiss")
    def dismiss(suggestion_id: int, request: Request) -> dict:
        user = _person(request)
        selected = _mailbox_row(request)
        if not leads.suggestion_in(conn, suggestion_id, int(selected["id"])):
            raise HTTPException(404, "建议不存在或已处理")
        try:
            leads.dismiss(conn, suggestion_id, user)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"ok": True}

    def _drafting_thread(thread_id: int, request: Request) -> sqlite3.Row:
        selected = _mailbox_row(request)
        if "draft" not in _mailbox_tasks(selected["address"]):
            raise HTTPException(404, "这个邮箱没开起草")
        if repo.get_thread(conn, thread_id, int(selected["id"])) is None:
            raise HTTPException(404, "没有这条线程")
        return selected

    @app.get("/api/threads/{thread_id}/draft")
    def get_draft(thread_id: int, request: Request) -> dict:
        _drafting_thread(thread_id, request)
        return {"draft": _draft_out(draft_mod.latest_draft(conn, thread_id))}

    @app.post("/api/threads/{thread_id}/draft")
    def make_draft(thread_id: int, request: Request) -> dict:
        _person(request)
        _drafting_thread(thread_id, request)
        draft_id = draft_mod.make_draft(conn, thread_id)
        row = conn.execute("SELECT * FROM reply_draft WHERE id = ?", (draft_id,)).fetchone()
        return {"draft": _draft_out(row)}

    @app.post("/api/threads/{thread_id}/send-token")
    def send_token(thread_id: int, request: Request) -> dict:
        """一次性令牌:只签给人,绑定线程,十分钟有效。后台任务没有请求,也就没有令牌。"""
        selected = _mailbox_row(request)
        if repo.get_thread(conn, thread_id, int(selected["id"])) is None:
            raise HTTPException(404, "没有这条线程")
        _authorize_sender(request)
        _authorize_followup_owner(request, thread_id)
        token = tokens.mint(thread_id, _person(request))
        return {"token": token.value, "expires_in": send_mod.TOKEN_TTL_SECONDS}

    @app.post("/api/threads/{thread_id}/send")
    def send(thread_id: int, request: Request, payload: SendBody) -> dict:
        user = _person(request)
        selected = _mailbox_row(request)
        if repo.get_thread(conn, thread_id, int(selected["id"])) is None:
            raise HTTPException(404, "没有这条线程")
        account = _authorize_sender(request)
        _authorize_followup_owner(request, thread_id)
        if account.transport is None or not account.address:
            raise HTTPException(503, "没有配置 SMTP,发不了")
        try:
            token = tokens.consume(payload.token, thread_id, user)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        try:
            send_mod.send(
                conn,
                token=token,
                mailbox_id=int(selected["id"]),
                sender=account.address,
                sender_name=account.display_name,
                thread_id=thread_id,
                to=payload.to,
                subject=payload.subject,
                body=payload.body,
                transport=account.transport,
                draft_id=int(payload.draft_id) if payload.draft_id else None,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        row = repo.get_thread(conn, thread_id, int(selected["id"]))
        assert row is not None
        return _thread_out(conn, row, with_messages=True)

    def _authorize_followup_owner(request: Request, thread_id: int) -> None:
        state = followup.get(conn, thread_id)
        if state and (
            not require_oa_auth
            or state["owner"] != request.headers.get("x-oa-email", "").strip().casefold()
        ):
            raise HTTPException(403, "会话已交接，只能由当前负责人回复")

    def _authorize_sender(request: Request) -> SendingAccount:
        identity = request.headers.get("x-oa-email", "").strip().casefold()
        if require_oa_auth and sending_accounts and identity in sending_accounts:
            account = sending_accounts[identity]
            if account.address.casefold() != identity:
                raise HTTPException(403, "发件身份不匹配")
            try:
                send_mod.validate_sender(account.address)
            except PermissionError as exc:
                raise HTTPException(403, str(exc)) from exc
            return account
        try:
            send_mod.validate_sender(sender)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        if (
            require_oa_auth
            and request.headers.get("x-oa-email", "").strip().casefold()
            != sender.strip().casefold()
        ):
            raise HTTPException(403, "当前账号未获授权使用这个发件邮箱")
        return SendingAccount(sender, sender_name, transport)

    @app.patch("/api/leads/{lead_id}")
    def patch_lead(lead_id: int, request: Request, patch: LeadPatch) -> dict:
        user = _person(request)
        selected = _mailbox_row(request)
        if not leads.lead_in(conn, lead_id, int(selected["id"])):
            raise HTTPException(404, "线索不存在")
        try:
            leads.update_lead(conn, lead_id, user, patch.status, patch.next_step)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        row = conn.execute("SELECT * FROM lead WHERE id = ?", (lead_id,)).fetchone()
        return _lead_out(row)

    from mail2leads.api.outreach import install as install_outreach

    install_outreach(
        app,
        conn,
        mailbox_id,
        _person,
        import_token=outreach_import_token,
        enabled=outreach_enabled,
        sender=sender,
        require_proxy=require_oa_auth,
        approval_proxy_key=outreach_approval_proxy_key,
        members=followup_members,
        sending_account=_authorize_sender,
    )

    if require_oa_auth and followup_members:
        from mail2leads.api.followup import install as install_followup

        install_followup(
            app, conn, _person, _mailbox_row, _thread_out, followup_members, _authorize_sender
        )

    if web_dist and (web_dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str) -> FileResponse:
            # history 路由:所有非 API 路径都回 index.html,前端自己认路
            return FileResponse(web_dist / "index.html")

    return app
