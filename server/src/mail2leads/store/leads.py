"""线索的读写。写 lead 的每个函数都要求 user:后台任务没有这个参数可传(宪法第五条)。"""

from __future__ import annotations

import json
import sqlite3

from mail2leads.store.repo import now_iso

LEAD_STATUSES = ("quote", "quoted", "following", "won", "lost")


def insert_suggestion(
    conn: sqlite3.Connection,
    source_id: int,
    thread_id: int,
    model: str,
    task_version: str,
    produced_at: str,
    payload: dict | None,
    reason: str = "",
) -> int:
    cur = conn.execute(
        "INSERT INTO lead_suggestion "
        "(source_id, thread_id, model, task_version, produced_at, status, payload, reason) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            source_id,
            thread_id,
            model,
            task_version,
            produced_at,
            "open" if payload is not None else "failed",
            json.dumps(payload or {}, ensure_ascii=False),
            reason,
        ),
    )
    return int(cur.lastrowid)


def open_suggestions(conn: sqlite3.Connection, mailbox_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT s.* FROM lead_suggestion s JOIN thread t ON t.id = s.thread_id "
        "WHERE t.mailbox_id = ? AND s.status = 'open' ORDER BY s.produced_at DESC",
        (mailbox_id,),
    ).fetchall()


def failed_suggestions(conn: sqlite3.Connection, mailbox_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM lead_suggestion s JOIN thread t ON t.id = s.thread_id "
        "WHERE t.mailbox_id = ? AND s.status = 'failed'",
        (mailbox_id,),
    ).fetchone()
    return int(row[0])


def get_suggestion(conn: sqlite3.Connection, suggestion_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM lead_suggestion WHERE id = ?", (suggestion_id,)).fetchone()


def _require_user(user: str) -> str:
    user = (user or "").strip()
    if not user:
        raise PermissionError("写线索必须带人的身份;后台任务没有")
    return user


def confirm(
    conn: sqlite3.Connection, suggestion_id: int, user: str, overrides: dict | None = None
) -> int:
    """建议 → 事实。只有人能做:user 为空直接拒绝。可以顺手改字段(overrides)。"""
    user = _require_user(user)
    s = get_suggestion(conn, suggestion_id)
    if s is None or s["status"] != "open":
        raise LookupError("建议不存在或已处理")
    payload = json.loads(s["payload"])
    payload.update(
        {
            k: v
            for k, v in (overrides or {}).items()
            if k in {"company", "contact", "wants", "quantity", "region"}
        }
    )
    thread = conn.execute(
        "SELECT mailbox_id FROM thread WHERE id = ?", (s["thread_id"],)
    ).fetchone()
    at = now_iso()
    conn.execute("BEGIN")
    try:
        cur = conn.execute(
            "INSERT INTO lead (mailbox_id, thread_id, suggestion_id, company, contact, wants, "
            "quantity, region, status, next_step, confirmed_by, confirmed_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'quote', '', ?, ?, ?)",
            (
                int(thread["mailbox_id"]),
                int(s["thread_id"]),
                suggestion_id,
                payload.get("company", ""),
                payload.get("contact", ""),
                payload.get("wants", ""),
                payload.get("quantity", ""),
                payload.get("region", ""),
                user,
                at,
                at,
            ),
        )
        conn.execute(
            "UPDATE lead_suggestion SET status = 'confirmed', decided_by = ?, decided_at = ? "
            "WHERE id = ?",
            (user, at, suggestion_id),
        )
        conn.execute("UPDATE thread SET folder = 'quote' WHERE id = ?", (s["thread_id"],))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return int(cur.lastrowid)


def dismiss(conn: sqlite3.Connection, suggestion_id: int, user: str) -> None:
    user = _require_user(user)
    changed = conn.execute(
        "UPDATE lead_suggestion SET status = 'dismissed', decided_by = ?, decided_at = ? "
        "WHERE id = ? AND status = 'open'",
        (user, now_iso(), suggestion_id),
    ).rowcount
    if not changed:
        raise LookupError("建议不存在或已处理")


def update_lead(
    conn: sqlite3.Connection,
    lead_id: int,
    user: str,
    status: str | None = None,
    next_step: str | None = None,
) -> None:
    _require_user(user)
    if status is not None and status not in LEAD_STATUSES:
        raise ValueError(f"状态只能是 {LEAD_STATUSES}")
    sets, args = ["updated_at = ?"], [now_iso()]
    if status is not None:
        sets.append("status = ?")
        args.append(status)
    if next_step is not None:
        sets.append("next_step = ?")
        args.append(next_step)
    args.append(lead_id)
    changed = conn.execute(f"UPDATE lead SET {', '.join(sets)} WHERE id = ?", args).rowcount
    if not changed:
        raise LookupError("线索不存在")


def list_leads(conn: sqlite3.Connection, mailbox_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM lead WHERE mailbox_id = ? ORDER BY updated_at DESC", (mailbox_id,)
    ).fetchall()
