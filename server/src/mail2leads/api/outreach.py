"""Machine imports are separate from human approval; neither can forge the other."""

import secrets
from contextlib import contextmanager

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from mail2leads import outreach
from mail2leads.send import TokenBox
from mail2leads.store.db import connect


class Approval(BaseModel):
    token: str = Field(max_length=200)
    steps: list[dict] = Field(min_length=6, max_length=6)
    policy_confirmed: bool = False


class Stop(BaseModel):
    reason: str = "paused"


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
):
    outreach.init(conn)
    path = conn.execute("PRAGMA database_list").fetchone()["file"]
    tokens = TokenBox()

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

    def human(request):
        actor = identity(request)
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
        with database() as c:
            return {
                "items": outreach.listing(c, mailbox_id),
                "enabled": enabled,
                "cadence_days": outreach.CADENCE,
                "sender": sender,
            }

    @app.post("/api/prospects/{sid}/approval-token")
    def approval_token(sid: str, request: Request):
        actor = human(request)
        try:
            with database() as c:
                outreach.get(c, mailbox_id, sid)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        token = tokens.mint(sid, actor)
        return {"token": token.value}

    @app.post("/api/prospects/{sid}/approve")
    def approve(sid: str, body: Approval, request: Request):
        actor = human(request)
        try:
            tokens.consume(body.token, sid, actor)
            with database() as c:
                outreach.approve(
                    c, mailbox_id, sid, actor, body.steps, body.policy_confirmed, sender=sender
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
                outreach.stop(c, mailbox_id, sid, body.reason, actor)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"ok": True}
