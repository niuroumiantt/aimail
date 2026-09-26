"""Loopback-only, bounded real-mail pilot. No send/delete routes or background polling."""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from aimail import backends, fact_store, translation_store
from aimail.ingest.imap import ImapSource
from aimail.ingest.run import store_raw
from aimail.paths import local_gateway_config, pilot_data_directory
from aimail.pilot import bounded_raw, read_env, recent_uids
from aimail.store import repo
from aimail.store.db import connect
from aimail.tasks import ask_mailbox
from aimail.tasks.read import read_message


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


def create_local_app(directory: Path, *, automatic: bool = False) -> FastAPI:
    stopped = threading.Event()
    processing = {"enabled": automatic}

    @asynccontextmanager
    async def lifespan(app):
        if db.exists():
            conn = connection()
            conn.execute(
                "CREATE TABLE IF NOT EXISTS extraction_setting "
                "(id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL)"
            )
            conn.execute("INSERT OR IGNORE INTO extraction_setting VALUES(1,?)", (int(automatic),))
            processing["enabled"] = bool(
                conn.execute("SELECT enabled FROM extraction_setting WHERE id=1").fetchone()[0]
            )
            conn.execute("UPDATE mail_fact_reading SET status='queued' WHERE status='running'")
            conn.close()
        worker = threading.Thread(target=background, daemon=True)
        worker.start()
        yield
        stopped.set()
        worker.join(timeout=2)
        executor.shutdown(wait=False)

    app = FastAPI(title="aimail local read-only pilot", lifespan=lifespan)
    executor = ThreadPoolExecutor(max_workers=1)
    lock = threading.Lock()
    job: dict = {"status": "idle", "kind": "", "error": None}
    db = directory / "mailbox.sqlite3"

    def event(kind, turn_id, payload):
        conn = connection()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS assistant_event "
                "(id INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, "
                "turn_id TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO assistant_event(at,kind,turn_id,payload) VALUES(?,?,?,?)",
                (
                    datetime.now(UTC).isoformat(),
                    kind,
                    turn_id,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            for operation in ("UPDATE", "DELETE"):
                conn.execute(
                    f"CREATE TRIGGER IF NOT EXISTS assistant_no_{operation.lower()} "
                    f"BEFORE {operation} ON assistant_event BEGIN "
                    "SELECT RAISE(ABORT, 'assistant audit is append-only'); END"
                )
        finally:
            conn.close()

    def conversation():
        conn = connection()
        try:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='assistant_event'"
            ).fetchone()
            if not exists:
                return []
            rows = conn.execute(
                "SELECT * FROM assistant_event WHERE id > "
                "COALESCE((SELECT MAX(id) FROM assistant_event WHERE kind='clear'),0) ORDER BY id"
            ).fetchall()
            turns = {}
            for row in rows:
                key = row["turn_id"]
                if row["kind"] == "question":
                    turns[key] = {
                        "id": key,
                        "at": row["at"],
                        "status": "running",
                        **json.loads(row["payload"]),
                    }
                elif key in turns:
                    turns[key].update(json.loads(row["payload"]))
            return list(turns.values())
        finally:
            conn.close()

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = request.headers.get("host", "")
        origin = request.headers.get("origin")
        allowed_hosts = {"127.0.0.1:8910", "localhost:8910", "testserver"}
        if host not in allowed_hosts or (
            origin
            and origin
            not in {
                "http://127.0.0.1:5197",
                "http://localhost:5197",
                "http://127.0.0.1:8910",
                "http://localhost:8910",
            }
        ):
            return JSONResponse({"detail": "Local access only"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    def connection():
        if not db.exists():
            raise HTTPException(503, "尚未导入真实邮件")
        conn = connect(db)
        fact_store.prepare(conn)
        translation_store.prepare(conn)
        return conn

    def background():
        while not stopped.wait(5):
            if not processing["enabled"] or not db.exists():
                continue
            conn = connection()
            try:
                row = conn.execute(
                    "SELECT source_id FROM mail_fact_reading WHERE status='queued' "
                    "ORDER BY source_id LIMIT 1"
                ).fetchone()
            finally:
                conn.close()
            if not row:
                continue

            def work(source_id=row["source_id"]):
                conn = connection()
                try:
                    status = fact_store.process(conn, source_id)
                    if status == "failed":
                        processing["enabled"] = False
                        conn.execute("UPDATE extraction_setting SET enabled=0 WHERE id=1")
                    return {"status": status}
                finally:
                    conn.close()

            try:
                start("extract", work)
            except HTTPException:
                pass  # Foreground sync/ask owns the single inference slot.

    @app.get("/mail/extraction")
    def extraction_status():
        conn = connection()
        try:
            return {**processing, "counts": fact_store.counts(conn)}
        finally:
            conn.close()

    @app.post("/mail/extraction/{action}")
    def extraction_control(action: str):
        if action not in {"pause", "resume"}:
            raise HTTPException(400, "不支持的操作")
        if action == "resume":
            conn = connection()
            try:
                conn.execute("UPDATE mail_fact_reading SET status='queued' WHERE status='failed'")
            finally:
                conn.close()
        processing["enabled"] = action == "resume"
        conn = connection()
        try:
            conn.execute(
                "UPDATE extraction_setting SET enabled=? WHERE id=1", (int(processing["enabled"]),)
            )
        finally:
            conn.close()
        event("extraction_control", "", {"actor": "local-user", "action": action})
        return extraction_status()

    def reading(conn, message_id):
        row = repo.latest_reading(conn, message_id)
        if row:
            return {
                "status": row["status"],
                "model": row["model"],
                "produced_at": row["produced_at"],
                "task_version": row["task_version"],
                "payload": json.loads(row["payload"]),
                "reason": "分析未成功，请重试" if row["status"] == "failed" else "",
            }
        file = directory / "latest-reading.json"
        if file.exists():
            cached = json.loads(file.read_text())
            if cached.get("source_id") == message_id:
                return {
                    "status": "ok",
                    "model": cached["model"],
                    "produced_at": cached["started_at"],
                    "task_version": cached["task_version"],
                    "payload": {**cached["summary"], "unverified": cached["unverified"]},
                    "coverage": "正文分析，未含附件",
                }
        return None

    @app.get("/mail/threads")
    def threads():
        conn = connection()
        try:
            mailbox = conn.execute("SELECT * FROM mailbox ORDER BY id LIMIT 1").fetchone()
            if not mailbox:
                return {"address": "", "threads": [], "messages": 0, "job": dict(job)}
            items = []
            for row in repo.list_threads(conn, mailbox["id"]):
                mails = repo.thread_messages(conn, row["id"])
                latest = mails[-1]
                items.append(
                    {
                        "id": row["id"],
                        "subject": row["subject"],
                        "contact": row["contact_name"] or row["contact_email"],
                        "email": row["contact_email"],
                        "date": row["last_at"],
                        "count": len(mails),
                        "preview": latest["body_new"][:160],
                        "reading": reading(conn, latest["id"]),
                    }
                )
            return {
                "address": mailbox["address"],
                "threads": items,
                "messages": sum(x["count"] for x in items),
                "job": dict(job),
                "coverage": "INBOX · 最近 30 天 · 每次最多 30 封 · 单封上限 2 MB",
            }
        finally:
            conn.close()

    @app.get("/mail/threads/{thread_id}")
    def detail(thread_id: int):
        conn = connection()
        try:
            row = conn.execute("SELECT * FROM thread WHERE id=?", (thread_id,)).fetchone()
            if not row:
                raise HTTPException(404, "邮件不存在")
            mails = []
            for m in repo.thread_messages(conn, thread_id):
                files = conn.execute(
                    "SELECT id,filename,size FROM attachment WHERE message_id=?", (m["id"],)
                ).fetchall()
                mails.append(
                    {
                        k: m[k]
                        for k in (
                            "id",
                            "subject",
                            "from_name",
                            "from_email",
                            "to_emails",
                            "sent_at",
                            "direction",
                            "body_new",
                            "body_quoted",
                        )
                    }
                    | {
                        "attachments": [dict(f) for f in files],
                        "reading": reading(conn, m["id"]),
                        "extraction": fact_store.get(conn, m["id"]),
                        "translation": translation_store.get(conn, m["id"]),
                    }
                )
            return {"id": row["id"], "messages": mails}
        finally:
            conn.close()

    def start(kind, function):
        with lock:
            if job["status"] == "running":
                raise HTTPException(409, "已有任务运行，请等待完成")
            job.update(status="running", kind=kind, error=None, result=None)

        def run():
            try:
                result = function()
                with lock:
                    job.update(status="done", result=result)
            except Exception as exc:
                with lock:
                    job.update(status="failed", error=type(exc).__name__)

        executor.submit(run)
        return {"accepted": True}

    @app.get("/mail/job")
    def job_status():
        with lock:
            return dict(job)

    @app.get("/mail/assistant")
    def assistant_history():
        return {"turns": conversation(), "job": job_status()}

    @app.post("/mail/assistant/clear")
    def assistant_clear():
        with lock:
            if job["status"] == "running":
                raise HTTPException(409, "任务进行中，请完成后再清屏")
            event("clear", "", {"actor": "local-user", "retained": True})
        return {"ok": True}

    @app.post("/mail/assistant")
    def assistant_ask(body: AskRequest):
        question = body.question.strip()
        if not question:
            raise HTTPException(422, "请输入问题")
        previous = conversation()[-2:]
        history = [
            {"question": t["question"], "findings": t.get("findings", [])}
            for t in previous
            if t["status"] == "done"
        ]
        turn_id = str(uuid4())

        def work():
            event("question", turn_id, {"question": question, "actor": "local-user"})
            try:
                conn = connection()
                try:
                    rows = conn.execute(
                        "SELECT id,thread_id,subject,from_email,sent_at,body_new "
                        "FROM message WHERE mailbox_id="
                        "(SELECT id FROM mailbox ORDER BY id LIMIT 1) "
                        "ORDER BY sent_at DESC,id DESC"
                    ).fetchall()
                    included = rows[:60]
                    budget = min(3000, 48000 // max(len(included), 1))
                    sources = [
                        {
                            "id": r["id"],
                            "thread_id": r["thread_id"],
                            "subject": r["subject"],
                            "sent_at": r["sent_at"],
                            "text": (r["subject"] + "\n" + r["from_email"] + "\n" + r["body_new"])[
                                :budget
                            ],
                        }
                        for r in included
                    ]
                    truncated = sum(
                        len(r["subject"] + r["from_email"] + r["body_new"]) + 2 > budget
                        for r in included
                    )
                finally:
                    conn.close()
                result = {
                    "status": "done",
                    "findings": ask_mailbox.ask(question, sources, history),
                    "model": backends.describe(),
                    "task_version": ask_mailbox.TASK_VERSION,
                    "produced_at": datetime.now(UTC).isoformat(),
                    "scope": {
                        "total": len(rows),
                        "included": len(sources),
                        "truncated": truncated,
                        "attachments": False,
                    },
                    "source_ids": [s["id"] for s in sources],
                }
                event("answer", turn_id, result)
                return {"status": "ok", "turn_id": turn_id}
            except Exception as exc:
                event(
                    "failure",
                    turn_id,
                    {
                        "status": "failed",
                        "error": "分析失败或引用未通过核对，请重试。",
                        "error_type": type(exc).__name__,
                    },
                )
                raise

        return {**start("ask", work), "turn_id": turn_id}

    @app.post("/mail/threads/{thread_id}/analyze")
    def analyze(thread_id: int):
        conn = connection()
        try:
            mails = repo.thread_messages(conn, thread_id)
            if not mails:
                raise HTTPException(404, "邮件不存在")
            message_id = mails[-1]["id"]
        finally:
            conn.close()

        def work():
            conn = connection()
            try:
                return {"status": read_message(conn, message_id, tasks=frozenset({"read"}))}
            finally:
                conn.close()

        return start("analyze", work)

    @app.post("/mail/messages/{message_id}/translate")
    def translate(message_id: int):
        def work():
            conn = connection()
            try:
                return {"status": translation_store.translate(conn, message_id)}
            finally:
                conn.close()

        return start("translate", work)

    @app.post("/mail/sync")
    def sync():
        def work():
            cfg = read_env(Path.home() / ".local/state/oa/sales-leads-preview/mailbox.env")
            conn = connection()
            source = None
            counts = {"stored": 0, "duplicate": 0, "oversize": 0}
            try:
                address = cfg["KEEL_CRM_MAILBOX_ADDRESS"]
                mailbox_id = repo.ensure_mailbox(conn, address)
                source = ImapSource(
                    cfg["KEEL_CRM_MAILBOX_IMAP_HOST"],
                    993,
                    address,
                    cfg["KEEL_CRM_MAILBOX_PASSWORD"],
                    "INBOX",
                )
                for uid in recent_uids(source, 30, 30):
                    raw = bounded_raw(source, uid)
                    if raw is None:
                        counts["oversize"] += 1
                        continue
                    pk, _ = store_raw(conn, mailbox_id, raw, "in", datetime.now(UTC))
                    counts["stored" if pk else "duplicate"] += 1
                return counts
            finally:
                if source:
                    source.close()
                conn.close()

        return start("sync", work)

    if db.exists():
        for turn in conversation():
            if turn["status"] == "running":
                event(
                    "failure",
                    turn["id"],
                    {"status": "failed", "error": "服务重启中断了上次请求，请重新提问。"},
                )
    return app


def main():
    import uvicorn

    os.umask(0o077)
    cfg = read_env(local_gateway_config())
    # Business tasks only see the gateway contract. No direct Ollama or Spark access.
    os.environ.update(
        LLM_BACKEND="local",
        LOCAL_MODEL=cfg["KEEL_AI_UPSTREAM_MODEL"],
        LOCAL_BASE_URL=cfg["KEEL_AI_UPSTREAM_URL"].removesuffix("/chat/completions"),
        LOCAL_API_KEY=cfg["KEEL_AI_UPSTREAM_TOKEN"],
        LOCAL_TIMEOUT="610",
        LOCAL_PROVIDER_LABEL="本机 API",
        MAIL_TRANSLATION_MODEL=cfg.get("MAIL_TRANSLATION_MODEL", ""),
    )
    app = create_local_app(pilot_data_directory(), automatic=True)
    uvicorn.run(app, host="127.0.0.1", port=8910)


if __name__ == "__main__":
    main()
