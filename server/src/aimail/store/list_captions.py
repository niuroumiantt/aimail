"""Cached Chinese list descriptions. Original messages and subjects remain immutable."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from aimail.ingest import quote
from aimail.tasks.list_caption import TASK_VERSION


def source(conn: sqlite3.Connection, thread_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id,subject,body_new,body_quoted FROM message WHERE thread_id=? "
        "ORDER BY (direction='in') DESC,sent_at DESC,id DESC LIMIT 1",
        (thread_id,),
    ).fetchone()


def get(conn: sqlite3.Connection, thread_id: int, source_id: int | None = None) -> dict | None:
    if source_id is None:
        message = source(conn, thread_id)
        source_id = int(message["id"]) if message else None
    row = conn.execute(
        "SELECT status,text_zh,reason,model,task_version,produced_at,source_id "
        "FROM mail_list_caption "
        "WHERE thread_id=? AND source_id=? AND task_version=?",
        (thread_id, source_id, TASK_VERSION),
    ).fetchone()
    return dict(row) if row else None


def claim(
    conn: sqlite3.Connection,
    ids: list[int],
    *,
    backend: str,
    model: str,
    retry: bool = False,
    raw_model: str | None = None,
) -> list[dict]:
    jobs = []
    now = datetime.now(UTC)
    for thread_id in ids:
        message = source(conn, thread_id)
        if message is None:
            continue
        cached = get(conn, thread_id, int(message["id"]))
        if cached:
            if cached["status"] == "ok" or (cached["status"] == "failed" and not retry):
                continue
            if cached["status"] == "pending" and datetime.fromisoformat(
                cached["produced_at"]
            ) > now - timedelta(minutes=5):
                continue
        token = uuid4().hex
        conn.execute(
            "INSERT INTO mail_list_caption(thread_id,source_id,status,text_zh,reason,model,"
            "task_version,produced_at,token) VALUES(?,?,'pending','','',?,?,?,?) "
            "ON CONFLICT(thread_id) DO UPDATE SET source_id=excluded.source_id,"
            "status='pending',text_zh='',reason='',model=excluded.model,"
            "task_version=excluded.task_version,produced_at=excluded.produced_at,"
            "token=excluded.token",
            (thread_id, message["id"], model, TASK_VERSION, now.isoformat(), token),
        )
        jobs.append(
            {
                "id": thread_id,
                "token": token,
                "backend": backend,
                "raw_model": raw_model,
                "subject": message["subject"],
                "body": quote.readable_body(message["body_new"], message["body_quoted"])[:6000],
            }
        )
    return jobs


def finish(conn: sqlite3.Connection, jobs: list[dict], result: dict[int, str] | None) -> None:
    for job in jobs:
        conn.execute(
            "UPDATE mail_list_caption SET status=?,text_zh=?,reason=?,produced_at=? "
            "WHERE thread_id=? AND token=?",
            (
                "ok" if result else "failed",
                result[job["id"]] if result else "",
                "中文描述生成失败，请重试" if result is None else "",
                datetime.now(UTC).isoformat(),
                job["id"],
                job["token"],
            ),
        )
