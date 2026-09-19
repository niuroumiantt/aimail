"""只读 API + 托管前端。人的两个动作(确认线索、发送)在 M4/M5 加进来。

JSON 形状与 web/src/data/types.ts 一致:界面不知道也不该知道数据库长什么样。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mail2leads.store import repo


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
        out["messages"] = [
            {
                "id": str(m["id"]),
                "direction": m["direction"],
                "from_name": m["from_name"] or m["from_email"],
                "from_email": m["from_email"],
                "sent_at": m["sent_at"],
                "body": m["body_new"],
                "quoted": m["body_quoted"] or None,
                "attachments": repo.attachment_names(conn, int(m["id"])) or None,
            }
            for m in messages
        ]
    return out


def create_app(conn: sqlite3.Connection, mailbox_id: int, web_dist: Path | None = None) -> FastAPI:
    app = FastAPI(title="mail2leads")

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

    @app.get("/api/leads/suggestions")
    def suggestions() -> list[dict]:
        return []  # M4

    @app.get("/api/leads")
    def leads() -> list[dict]:
        return []  # M4

    if web_dist and (web_dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str) -> FileResponse:
            # history 路由:所有非 API 路径都回 index.html,前端自己认路
            return FileResponse(web_dist / "index.html")

    return app
