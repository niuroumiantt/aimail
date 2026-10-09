"""Mailbox-scoped registration UI and a separate versioned downstream contract."""

from __future__ import annotations

import json
import secrets
import threading
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from aimail import backends
from aimail.store import crm, model_selection, repo
from aimail.store.db import connect
from aimail.tasks import register_contact


class Receipt(BaseModel):
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    account_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,150}$")
    company_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,150}$")


def install(app, conn, person, mailbox, *, token="", lock=None):
    path = next((r[2] for r in conn.execute("PRAGMA database_list") if r[1] == "main"), "")

    def thread(tid, request):
        selected = mailbox(request)
        if repo.get_thread(conn, tid, int(selected["id"])) is None:
            raise HTTPException(404, "没有这条会话")
        return int(selected["id"])

    def human(request):
        user = person(request)
        origin = request.headers.get("origin")
        if origin and origin not in {
            "https://" + request.headers.get("host", ""),
            "http://" + request.headers.get("host", ""),
        }:
            raise HTTPException(403, "不接受跨站建档")
        return request.headers.get("x-oa-email", "").strip().casefold() or user

    def machine(request):
        if not token or not secrets.compare_digest(
            request.headers.get("authorization", ""), "Bearer " + token
        ):
            raise HTTPException(401, "需要集成令牌")

    @app.get("/api/threads/{tid}/registration")
    def get(tid: int, request: Request):
        thread(tid, request)
        return crm.state(conn, tid)

    @app.post("/api/threads/{tid}/registration")
    def save(tid: int, payload: crm.Registration, request: Request):
        mid, actor = thread(tid, request), human(request)
        if not token:
            raise HTTPException(503, "客户档案同步尚未配置")
        try:
            return crm.save(conn, tid, mid, payload, actor)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e

    @app.post("/api/threads/{tid}/registration/extract")
    def extract(tid: int, request: Request):
        mid = thread(tid, request)
        human(request)
        state = crm.state(conn, tid)
        if (
            state["registration"]
            or state["suggestion"]
            and state["suggestion"]["status"] == "running"
        ):
            return state
        evidence = crm.sources(conn, tid)
        if not evidence:
            raise HTTPException(422, "没有可提取的原文")
        generation = uuid4().hex
        at = datetime.now(UTC).isoformat()
        with model_selection.use(conn, mid):
            ready, _ = backends.ready()
            if not ready:
                raise HTTPException(503, "模型暂不可用，可手动填写")
            model = backends.describe()
        conn.execute(
            "INSERT INTO crm_suggestion VALUES(?,?,?,?,?,?,?,'{}',?) ON "
            "CONFLICT(thread_id) DO UPDATE SET "
            "source_id=excluded.source_id,model=excluded.model,task_version=excluded.task_version,produced_at=excluded.produced_at,generation=excluded.generation,status=excluded.status,payload='{}',input_hash=excluded.input_hash",
            (
                tid,
                evidence[0]["id"],
                model,
                register_contact.TASK_VERSION,
                at,
                generation,
                "running",
                crm.fingerprint(evidence),
            ),
        )

        def run():
            worker = connect(path) if path else conn
            try:
                with model_selection.use(worker, mid):
                    result = register_contact.extract(evidence)
                status = "ok"
            except Exception:
                status, result = "failed", {"error": "提取失败，可重试或手动填写"}
            try:
                if lock:
                    lock.acquire()
                worker.execute(
                    "UPDATE crm_suggestion SET status=?,payload=? WHERE thread_id=? "
                    "AND generation=?",
                    (status, json.dumps(result, ensure_ascii=False), tid, generation),
                )
            finally:
                if lock:
                    lock.release()
                if path:
                    worker.close()

        threading.Thread(target=run, daemon=True).start()
        return crm.state(conn, tid)

    @app.get("/v1/contact-registrations")
    def feed(request: Request, after: int = 0, limit: int = 100):
        machine(request)
        rows = conn.execute(
            "SELECT * FROM crm_registration WHERE id>? ORDER BY id LIMIT ?",
            (max(0, after), min(200, max(1, limit))),
        ).fetchall()
        return {
            "version": "contact-registrations@1",
            "items": [crm.exported(conn, r) for r in rows],
            "next_after": rows[-1]["id"] if rows else after,
        }

    @app.post("/v1/contact-registrations/{rid}/receipt")
    def receipt(rid: int, body: Receipt, request: Request):
        machine(request)
        row = conn.execute("SELECT * FROM crm_registration WHERE id=?", (rid,)).fetchone()
        if not row or row["fingerprint"] != body.fingerprint:
            raise HTTPException(409, "建档回执版本不匹配")
        value = body.model_dump()
        existing = json.loads(row["receipt"])
        if existing and existing != value:
            raise HTTPException(409, "建档回执冲突")
        conn.execute("UPDATE crm_registration SET receipt=? WHERE id=?", (json.dumps(value), rid))
        return {"id": rid, **value}
