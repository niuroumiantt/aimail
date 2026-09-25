"""记忆是一次查询,不是一张模型写的表(ADR-0005)。

谁算"同一位客户"由代码裁决:同一个邮箱地址;或同一个公司域名——公共邮箱域(gmail、qq…)不算公司。
给模型看的历史只含原文摘录和我们自己记的状态:派生物不喂派生物,模型引用的数字仍能回到原文。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

# 公共邮箱域:同域不等于同公司。这是一个可穷举的常量表,不是语义规则
PUBLIC_MAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "yahoo.com",
        "yahoo.co.jp",
        "icloud.com",
        "me.com",
        "protonmail.com",
        "proton.me",
        "qq.com",
        "163.com",
        "126.com",
        "foxmail.com",
        "sina.com",
        "sohu.com",
        "aliyun.com",
        "mail.ru",
        "yandex.ru",
        "naver.com",
        "daum.net",
        "gmx.de",
        "web.de",
        "aol.com",
    }
)

FOLDER_WORD = {"inbox": "待处理", "quote": "待报价", "replied": "已回复", "invalid": "无效"}
LEAD_WORD = {
    "quote": "待报价",
    "quoted": "已报价",
    "following": "跟进中",
    "won": "成交",
    "lost": "丢单",
}
EXCERPT_CHARS = 240
HISTORY_HEADER = "——这位客户此前的往来(来自我们自己的记录,不是这封信)——"


def company_key(email: str) -> str:
    """同一位客户的判据:公司域名;公共邮箱域上只认整个地址。"""
    email = email.strip().lower()
    if "@" not in email:
        return email
    domain = email.rsplit("@", 1)[1]
    return email if domain in PUBLIC_MAIL_DOMAINS else domain


@dataclass(frozen=True)
class HistoryItem:
    thread_id: int
    subject: str
    contact_email: str
    first_at: str
    last_at: str
    folder: str
    replied: bool
    lead_status: str  # '' = 没有确认过的线索
    excerpt: str  # 最后一封来信的原文开头


def related_threads(
    conn: sqlite3.Connection, mailbox_id: int, thread_id: int, limit: int = 5
) -> list[HistoryItem]:
    """同一位客户在这个邮箱里的其他线程,最近的在前。别的邮箱看不见(M9 的前提)。"""
    me = conn.execute(
        "SELECT contact_email FROM thread WHERE id = ? AND mailbox_id = ?", (thread_id, mailbox_id)
    ).fetchone()
    if me is None:
        raise KeyError(f"邮箱 {mailbox_id} 里没有线程 {thread_id}")
    key = company_key(me["contact_email"])
    rows = conn.execute(
        "SELECT id, subject, contact_email, first_at, last_at, folder FROM thread "
        "WHERE mailbox_id = ? AND id <> ? ORDER BY last_at DESC, id DESC",
        (mailbox_id, thread_id),
    ).fetchall()
    items: list[HistoryItem] = []
    for r in rows:
        if company_key(r["contact_email"]) != key:
            continue
        items.append(_item(conn, r))
        if len(items) >= limit:
            break
    return items


def _item(conn: sqlite3.Connection, r: sqlite3.Row) -> HistoryItem:
    tid = int(r["id"])
    replied = (
        conn.execute(
            "SELECT 1 FROM message WHERE thread_id = ? AND direction = 'out' LIMIT 1", (tid,)
        ).fetchone()
        is not None
    )
    lead = conn.execute(
        "SELECT status FROM lead WHERE thread_id = ? ORDER BY updated_at DESC, id DESC LIMIT 1",
        (tid,),
    ).fetchone()
    last_in = conn.execute(
        "SELECT body_new FROM message WHERE thread_id = ? AND direction = 'in' "
        "ORDER BY sent_at DESC, id DESC LIMIT 1",
        (tid,),
    ).fetchone()
    excerpt = " ".join(str(last_in["body_new"]).split())[:EXCERPT_CHARS] if last_in else ""
    return HistoryItem(
        thread_id=tid,
        subject=str(r["subject"]),
        contact_email=str(r["contact_email"]),
        first_at=str(r["first_at"]),
        last_at=str(r["last_at"]),
        folder=str(r["folder"]),
        replied=replied,
        lead_status=str(lead["status"]) if lead else "",
        excerpt=excerpt,
    )


def history_text(items: list[HistoryItem]) -> str:
    """模型看到的历史段:只有原文摘录与我们记的状态。没有历史就是空串,不占提示词。"""
    if not items:
        return ""
    lines = [HISTORY_HEADER]
    for n, it in enumerate(items, 1):
        status = [FOLDER_WORD.get(it.folder, it.folder)]
        if it.lead_status:
            status.append(f"线索:{LEAD_WORD.get(it.lead_status, it.lead_status)}")
        lines.append(f"{n}. {it.first_at[:10]} · {it.subject} · {' · '.join(status)}")
        if it.excerpt:
            lines.append(f"   来信摘录:{it.excerpt}")
    return "\n".join(lines)


def for_thread(conn: sqlite3.Connection, mailbox_id: int, thread_id: int) -> str:
    return history_text(related_threads(conn, mailbox_id, thread_id))
