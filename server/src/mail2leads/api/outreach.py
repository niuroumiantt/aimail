"""Machine imports are separate from human approval; neither can forge the other."""

import secrets
from contextlib import contextmanager

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from mail2leads import outreach
from mail2leads.send import TokenBox, validate_sender
from mail2leads.store.db import connect


class Approval(BaseModel):
    token: str = Field(max_length=200)
    steps: list[dict] = Field(min_length=6, max_length=6)
    policy_confirmed: bool = False


class Stop(BaseModel):
    reason: str = "paused"


class Assignment(BaseModel):
    action: str = Field(max_length=16)
    recipient: str = Field(default="", max_length=320)
    version: int = Field(ge=0)


def install(
    app,
    conn,
    mailbox_id,
    person,
    *,
    import_token="",
    enabled=False,
    sender="",
    require_proxy=False,
    approval_proxy_key="",
    members=(),
    sending_account=None,
):
    outreach.init(conn)
    path = conn.execute("PRAGMA database_list").fetchone()["file"]
    tokens = TokenBox()
    members = frozenset(m.strip().casefold() for m in members if m.strip())

    @contextmanager
    def database():
        if not path:
            yield conn  # In-memory unit tests only.
            return
        c = connect(path)
        try:
            yield c
        finally:
            c.close()

    def machine(request):
        auth = request.headers.get("authorization", "")
        if not import_token or not secrets.compare_digest(auth, "Bearer " + import_token):
            raise HTTPException(401, "需要专用名单接口令牌")

    def identity(request):
        actor = person(request)
        if require_proxy and (
            not approval_proxy_key
            or not secrets.compare_digest(
                request.headers.get("x-outreach-approval-key", ""), approval_proxy_key
            )
        ):
            raise HTTPException(403, "开发信审核必须经过已配置的可信登录代理")
        return actor

    def personal_sender(request):
        return sending_account(request).address if require_proxy and sending_account else sender

    def owns(c, sid, request):
        outreach.get(c, mailbox_id, sid)
        if not require_proxy:
            return
        row = c.execute(
            "SELECT owner FROM prospect_assignment WHERE sequence_id=?", (sid,)
        ).fetchone()
        owner = row["owner"] if row else sender
        if owner.casefold() != request.headers.get("x-oa-email", "").strip().casefold():
            raise HTTPException(403, "只有当前负责人可以操作此潜客")

    def human(request):
        actor = identity(request)
        try:
            validate_sender(personal_sender(request))
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        if (
            require_proxy
            and request.headers.get("x-oa-email", "").strip().casefold()
            != personal_sender(request).strip().casefold()
        ):
            raise HTTPException(403, "当前账号未获授权使用这个发件邮箱")
        origin = request.headers.get("origin")
        host = request.headers.get("host", "")
        if request.headers.get("x-outreach-action") != "confirm-v1" or (
            origin and origin not in {"http://" + host, "https://" + host}
        ):
            raise HTTPException(403, "需要同站人工确认请求")
        return actor

    @app.post("/v1/prospects/import")
    async def import_one(request: Request):
        machine(request)
        body = await request.body()
        if len(body) > 32000:
            raise HTTPException(413)
        try:
            payload = await request.json()
            with database() as c:
                return outreach.import_prospect(c, mailbox_id, payload)
        except (ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/v1/outreach/events")
    def events(request: Request, cursor: int = 0):
        machine(request)
        with database() as c:
            return outreach.events(c, mailbox_id, max(0, cursor))

    @app.post("/v1/prospects/{sid}/stop")
    def machine_stop(sid: str, body: Stop, request: Request):
        machine(request)
        if body.reason not in {"paused", "unsubscribed"}:
            raise HTTPException(422, "名单接口只能暂停或退订")
        try:
            with database() as c, outreach.transaction(c):
                outreach.stop(c, mailbox_id, sid, body.reason, "list-operator")
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"ok": True}

    @app.get("/api/prospects")
    def prospects(request: Request):
        identity(request)
        try:
            current_sender = personal_sender(request)
        except HTTPException:
            current_sender = ""
        with database() as c:
            items = outreach.listing(c, mailbox_id)
            user = request.headers.get("x-oa-email", "").strip().casefold()
            if require_proxy and user != sender.casefold():
                items = [
                    item
                    for item in items
                    if item["assignment"]
                    and user in {item["assignment"]["owner"], item["assignment"]["pending"]}
                ]
            return {
                "items": items,
                "enabled": enabled,
                "cadence_days": outreach.CADENCE,
                "sender": current_sender,
                "default_owner": sender,
                "identity": request.headers.get("x-oa-email", "").strip().casefold(),
                "assignment_members": sorted(members) if require_proxy else [],
            }

    @app.post("/api/prospects/{sid}/approval-token")
    def approval_token(sid: str, request: Request):
        actor = human(request)
        try:
            with database() as c:
                owns(c, sid, request)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        token = tokens.mint(sid, actor)
        return {"token": token.value}

    @app.post("/api/prospects/{sid}/assignment")
    def assignment(sid: str, body: Assignment, request: Request):
        identity(request)
        actor = request.headers.get("x-oa-email", "").strip().casefold()
        recipient = body.recipient.strip().casefold()
        if not require_proxy or actor not in members or sender.casefold() not in members:
            raise HTTPException(403, "潜客分配需要已登记员工及可信身份代理")
        if body.action == "offer" and recipient not in members:
            raise HTTPException(422, "接收人不是已登记员工")
        try:
            with database() as c:
                return outreach.assign(
                    c,
                    mailbox_id,
                    sid,
                    actor,
                    sender.casefold(),
                    body.action,
                    recipient,
                    body.version,
                )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/prospects/{sid}/approve")
    def approve(sid: str, body: Approval, request: Request):
        actor = human(request)
        try:
            tokens.consume(body.token, sid, actor)
            with database() as c:
                owns(c, sid, request)
                outreach.approve(
                    c,
                    mailbox_id,
                    sid,
                    actor,
                    body.steps,
                    body.policy_confirmed,
                    sender=personal_sender(request),
                )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"ok": True}

    @app.post("/api/prospects/{sid}/stop")
    def stop(sid: str, body: Stop, request: Request):
        actor = human(request)
        try:
            with database() as c, outreach.transaction(c):
                owns(c, sid, request)
                outreach.stop(c, mailbox_id, sid, body.reason, actor)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"ok": True}
