"""推送发件箱:线索一变,同一事务里记一条事件;后台按退避重试投递,送没送到都看得见(宪法第六条)。

下游(OA、PO、合同)只收**事实**——lead 表的行;建议永远不出门(第五条)。
签名:HMAC-SHA256(secret, body),放在 X-Mail2leads-Signature: sha256=<hex>。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Protocol

EVENTS = ("lead.confirmed", "lead.updated")
BACKOFF_SECONDS = (60, 300, 1800, 7200, 43200)
MAX_BACKOFF = 86400
BATCH = 50


def _iso(t: datetime) -> str:
    return t.replace(microsecond=0).isoformat()


def enqueue(conn: sqlite3.Connection, mailbox_id: int, event: str, lead_id: int, lead: dict) -> int:
    """记一条待推送事件。调用方负责把它放进和写线索同一个事务里。"""
    if event not in EVENTS:
        raise ValueError(f"事件只能是 {EVENTS}")
    now = _iso(datetime.now(UTC))
    cur = conn.execute(
        "INSERT INTO outbox (mailbox_id, event, lead_id, payload, created_at, next_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (mailbox_id, event, lead_id, json.dumps(lead, ensure_ascii=False), now, now),
    )
    return int(cur.lastrowid)


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify(secret: str, body: bytes, signature: str) -> bool:
    """给下游抄的校验:常量时间比较。"""
    return hmac.compare_digest(sign(secret, body), signature or "")


def envelope(row: sqlite3.Row, secret: str) -> tuple[bytes, dict[str, str]]:
    """一次投递的 body 与请求头。重试时字节完全一样,下游按 X-Mail2leads-Delivery 去重。"""
    body = json.dumps(
        {
            "event": row["event"],
            "delivery": str(row["id"]),
            "created_at": row["created_at"],
            "lead": json.loads(row["payload"]),
        },
        ensure_ascii=False,
    ).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Mail2leads-Event": str(row["event"]),
        "X-Mail2leads-Delivery": str(row["id"]),
        "X-Mail2leads-Signature": sign(secret, body),
    }
    return body, headers


class Poster(Protocol):
    def post(self, body: bytes, headers: dict[str, str]) -> tuple[int, str]: ...


class HttpPoster:
    def __init__(self, url: str, timeout: float = 10.0) -> None:
        self.url, self.timeout = url, timeout

    def post(self, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
        import httpx

        r = httpx.post(self.url, content=body, headers=headers, timeout=self.timeout)
        return r.status_code, r.text[:200]


def backoff(attempts: int) -> int:
    return BACKOFF_SECONDS[attempts - 1] if attempts <= len(BACKOFF_SECONDS) else MAX_BACKOFF


def deliver_pending(
    conn: sqlite3.Connection,
    mailbox_id: int,
    poster: Poster,
    secret: str,
    now: datetime | None = None,
) -> tuple[int, int]:
    """投递到期的事件。返回 (送到的, 失败的)。失败只记原因和下次时间,永不丢事件。"""
    now = now or datetime.now(UTC)
    rows = conn.execute(
        "SELECT * FROM outbox WHERE mailbox_id = ? AND delivered_at IS NULL AND next_at <= ? "
        "ORDER BY id LIMIT ?",
        (mailbox_id, _iso(now), BATCH),
    ).fetchall()
    delivered = failed = 0
    for row in rows:
        body, headers = envelope(row, secret)
        try:
            status, text = poster.post(body, headers)
            error = "" if 200 <= status < 300 else f"HTTP {status} {text}".strip()
        except Exception as exc:  # noqa: BLE001 —— 网络错误是预期内的失败,记下来重试
            error = f"{type(exc).__name__}: {exc}"[:300]
        attempts = int(row["attempts"]) + 1
        if not error:
            delivered += 1
            conn.execute(
                "UPDATE outbox SET attempts = ?, delivered_at = ?, last_error = '' WHERE id = ?",
                (attempts, _iso(now), row["id"]),
            )
        else:
            failed += 1
            conn.execute(
                "UPDATE outbox SET attempts = ?, next_at = ?, last_error = ? WHERE id = ?",
                (attempts, _iso(now + timedelta(seconds=backoff(attempts))), error, row["id"]),
            )
    return delivered, failed


def status(conn: sqlite3.Connection, mailbox_id: int) -> dict:
    """给界面看的:多少没送到、最近一次为什么。"""
    row = conn.execute(
        "SELECT "
        "SUM(delivered_at IS NULL AND attempts = 0) AS pending, "
        "SUM(delivered_at IS NULL AND attempts > 0) AS failed, "
        "SUM(delivered_at IS NOT NULL) AS delivered "
        "FROM outbox WHERE mailbox_id = ?",
        (mailbox_id,),
    ).fetchone()
    last = conn.execute(
        "SELECT last_error FROM outbox WHERE mailbox_id = ? AND delivered_at IS NULL "
        "AND last_error <> '' ORDER BY id DESC LIMIT 1",
        (mailbox_id,),
    ).fetchone()
    return {
        "pending": int(row["pending"] or 0),
        "failed": int(row["failed"] or 0),
        "delivered": int(row["delivered"] or 0),
        "last_error": str(last["last_error"]) if last else "",
    }
