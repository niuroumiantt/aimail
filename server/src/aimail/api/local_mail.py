"""Read-only, revocable device exports. Scope is rechecked on every request."""

from __future__ import annotations

import hashlib
import json
import secrets

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, Field

from aimail.store import repo

SCHEMA = """
CREATE TABLE IF NOT EXISTS local_mail_device (
 id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, owner TEXT NOT NULL,
 name TEXT NOT NULL, mailboxes TEXT NOT NULL, created_at TEXT NOT NULL,
 revoked_at TEXT NOT NULL DEFAULT '', last_seen_at TEXT NOT NULL DEFAULT ''
);
"""


def create_device(conn, owner, name, addresses):
    token, device = secrets.token_urlsafe(48), secrets.token_hex(16)
    conn.execute(
        "INSERT INTO local_mail_device(id,token_hash,owner,name,mailboxes,created_at) "
        "VALUES(?,?,?,?,?,?)",
        (
            device,
            hashlib.sha256(token.encode()).hexdigest(),
            owner.casefold(),
            name,
            json.dumps(sorted(set(addresses))),
            repo.now_iso(),
        ),
    )
    return {"device_id": device, "token": token, "mailboxes": sorted(set(addresses))}


class Enrollment(BaseModel):
    name: str = Field(min_length=1, max_length=100)


def install(app, conn, person, access_for_owner):
    conn.executescript(SCHEMA)

    def scope(request):
        value = request.headers.get("authorization", "").removeprefix("Bearer ")
        device = conn.execute(
            "SELECT * FROM local_mail_device WHERE token_hash=? AND revoked_at=''",
            (hashlib.sha256(value.encode()).hexdigest(),),
        ).fetchone()
        if not device:
            raise HTTPException(401, "需要本机同步授权")
        allowed = set(json.loads(device["mailboxes"])) & set(access_for_owner(device["owner"]))
        ids = [r[0] for r in conn.execute("SELECT id,address FROM mailbox") if r[1] in allowed]
        if not ids:
            raise HTTPException(403, "本机已无邮箱访问权限")
        conn.execute(
            "UPDATE local_mail_device SET last_seen_at=? WHERE id=?", (repo.now_iso(), device["id"])
        )
        return ids

    @app.post("/api/local-mail/devices")
    def enroll(body: Enrollment, request: Request):
        person(request)
        owner = request.headers.get("x-oa-email", "").strip().casefold()
        if not owner:
            raise HTTPException(403, "需要已登录的邮箱身份")
        if request.headers.get("origin") not in {
            None,
            "https://" + request.headers.get("host", ""),
        }:
            raise HTTPException(403, "不接受跨站授权")
        addresses = access_for_owner(owner)
        if not addresses:
            raise HTTPException(403, "没有可同步的邮箱")
        return create_device(conn, owner, body.name, addresses)

    @app.get("/api/local-mail/devices")
    def devices(request: Request):
        person(request)
        owner = request.headers.get("x-oa-email", "").strip().casefold()
        return [
            dict(r)
            for r in conn.execute(
                "SELECT id,name,created_at,revoked_at,last_seen_at "
                "FROM local_mail_device WHERE owner=?",
                (owner,),
            )
        ]

    @app.delete("/api/local-mail/devices/{device_id}")
    def revoke(device_id: str, request: Request):
        person(request)
        owner = request.headers.get("x-oa-email", "").strip().casefold()
        if request.headers.get("origin") not in {
            None,
            "https://" + request.headers.get("host", ""),
        }:
            raise HTTPException(403, "不接受跨站操作")
        conn.execute(
            "UPDATE local_mail_device SET revoked_at=? WHERE id=? AND owner=?",
            (repo.now_iso(), device_id, owner),
        )
        return {"revoked": True}

    @app.get("/v1/local-mail/messages")
    def messages(request: Request, after: int = 0, limit: int = 100):
        ids = scope(request)
        marks = ",".join("?" for _ in ids)
        rows = conn.execute(
            "SELECT m.id,m.mailbox_id,b.address AS mailbox,m.thread_id,"
            "m.from_name,m.from_email,m.to_emails,m.subject,m.sent_at,"
            "m.direction,m.body_new,m.body_quoted,m.raw_sha256 "
            "FROM message m JOIN mailbox b ON b.id=m.mailbox_id WHERE "
            f"m.id>? AND m.mailbox_id IN ({marks}) ORDER BY m.id LIMIT ?",
            (max(0, after), *ids, min(200, max(1, limit))),
        ).fetchall()
        return {
            "version": "local-mail@1",
            "items": [dict(r) for r in rows],
            "next_after": rows[-1]["id"] if rows else after,
        }

    @app.get("/v1/local-mail/messages/{message_id}/original")
    def original(message_id: int, request: Request):
        ids = scope(request)
        row = conn.execute(
            "SELECT mailbox_id,raw FROM message WHERE id=?", (message_id,)
        ).fetchone()
        if not row or row[0] not in ids:
            raise HTTPException(404, "邮件不存在")
        return Response(
            bytes(row[1]), media_type="message/rfc822", headers={"Cache-Control": "no-store"}
        )

    @app.get("/v1/local-mail/translations")
    def translations(request: Request, after: int = 0, limit: int = 100):
        ids = scope(request)
        marks = ",".join("?" for _ in ids)
        rows = conn.execute(
            "SELECT t.* FROM message_translation t JOIN message m "
            "ON m.id=t.source_id WHERE t.id>? AND "
            f"m.mailbox_id IN ({marks}) ORDER BY t.id LIMIT ?",
            (max(0, after), *ids, min(200, max(1, limit))),
        ).fetchall()
        return {
            "version": "local-translations@1",
            "items": [dict(r) for r in rows],
            "next_after": rows[-1]["id"] if rows else after,
        }
