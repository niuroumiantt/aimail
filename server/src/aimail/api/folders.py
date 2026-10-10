"""Private, mailbox-scoped folders. Never mutate original mail or IMAP folders."""

import sqlite3
import unicodedata

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from aimail.store import repo


class FolderBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    parent_id: int | None = None


class MoveBody(BaseModel):
    folder_id: int | None = None


def install(app, conn, person, mailbox, require_oa_auth):
    def scope(request):
        actor = person(request)
        owner = (
            request.headers.get("x-oa-email", "").strip().casefold() if require_oa_auth else actor
        )
        if not owner:
            raise HTTPException(401, "请先登录再整理文件夹")
        return int(mailbox(request)["id"]), owner

    def find(folder_id, box, owner):
        row = conn.execute(
            "SELECT * FROM mail_folder WHERE id=? AND mailbox_id=? AND owner=?",
            (folder_id, box, owner),
        ).fetchone()
        if not row:
            raise HTTPException(404, "没有这个文件夹")
        return row

    def name_of(value):
        name = unicodedata.normalize("NFKC", value).strip()
        if not name or len(name) > 80 or any(unicodedata.category(c).startswith("C") for c in name):
            raise HTTPException(422, "文件夹名称请填写 1–80 个可显示字符")
        return name

    @app.get("/api/folders")
    def listing(request: Request):
        box, owner = scope(request)
        rows = conn.execute(
            "SELECT f.id,f.name,f.parent_id,sum(CASE WHEN m.thread_id IS NOT NULL "
            "AND coalesce(s.deleted_at,'')='' THEN 1 ELSE 0 END) AS count FROM mail_folder f "
            "LEFT JOIN mail_folder_member m ON m.folder_id=f.id "
            "LEFT JOIN thread_mail_state s ON s.thread_id=m.thread_id "
            "WHERE f.mailbox_id=? AND f.owner=? GROUP BY f.id ORDER BY f.name_key,f.id",
            (box, owner),
        ).fetchall()
        assignments = conn.execute(
            "SELECT m.thread_id,m.folder_id FROM mail_folder_member m "
            "JOIN mail_folder f ON f.id=m.folder_id WHERE f.mailbox_id=? AND f.owner=?",
            (box, owner),
        ).fetchall()
        return {
            "items": [
                {
                    **dict(r),
                    "id": str(r["id"]),
                    "parent_id": str(r["parent_id"]) if r["parent_id"] else None,
                }
                for r in rows
            ],
            "assignments": {str(r["thread_id"]): str(r["folder_id"]) for r in assignments},
        }

    @app.post("/api/folders")
    def create(body: FolderBody, request: Request):
        box, owner = scope(request)
        name = name_of(body.name)
        parent, depth = body.parent_id, 1
        while parent is not None:
            parent = find(parent, box, owner)["parent_id"]
            depth += 1
            if depth > 3:
                raise HTTPException(422, "最多创建三层文件夹")
        try:
            conn.execute(
                "INSERT INTO mail_folder(mailbox_id,owner,parent_id,name,name_key,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (box, owner, body.parent_id, name, name.casefold(), repo.now_iso()),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "同一层已有同名文件夹") from exc
        return listing(request)

    @app.patch("/api/folders/{folder_id}")
    def rename(folder_id: int, body: FolderBody, request: Request):
        box, owner = scope(request)
        find(folder_id, box, owner)
        name = name_of(body.name)
        try:
            conn.execute(
                "UPDATE mail_folder SET name=?,name_key=? WHERE id=?",
                (name, name.casefold(), folder_id),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "同一层已有同名文件夹") from exc
        return listing(request)

    @app.delete("/api/folders/{folder_id}")
    def remove(folder_id: int, request: Request):
        box, owner = scope(request)
        find(folder_id, box, owner)
        if (
            conn.execute("SELECT 1 FROM mail_folder WHERE parent_id=?", (folder_id,)).fetchone()
            or conn.execute(
                "SELECT 1 FROM mail_folder_member WHERE folder_id=?", (folder_id,)
            ).fetchone()
        ):
            raise HTTPException(409, "请先移出邮件并删除子文件夹；删除文件夹不会删除邮件")
        conn.execute("DELETE FROM mail_folder WHERE id=?", (folder_id,))
        return listing(request)

    @app.put("/api/threads/{thread_id}/folder")
    def move(thread_id: int, body: MoveBody, request: Request):
        box, owner = scope(request)
        if repo.get_thread(conn, thread_id, box) is None:
            raise HTTPException(404, "没有这条会话")
        if body.folder_id is not None:
            find(body.folder_id, box, owner)
            conn.execute(
                "INSERT INTO mail_folder_member(thread_id,owner,folder_id) VALUES(?,?,?) "
                "ON CONFLICT(thread_id,owner) DO UPDATE SET folder_id=excluded.folder_id",
                (thread_id, owner, body.folder_id),
            )
        else:
            conn.execute(
                "DELETE FROM mail_folder_member WHERE thread_id=? AND owner=?", (thread_id, owner)
            )
        return listing(request)
