"""线程归并。规则是确定性的(宪法第一条:生命周期归代码):

1. In-Reply-To 或 References 指向库里已有的信 → 同一线程
2. 否则:去掉 Re:/Fwd: 后主题相同、对方相同、60 天内有往来 → 同一线程
3. 否则新线程
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta

from mail2leads.ingest.parse import Parsed
from mail2leads.store import repo

PREFIX = re.compile(r"^\s*(?:(?:re|fw|fwd|aw|wg|sv|回复|答复|回覆|转发|轉發)\s*[:：]\s*)+", re.I)
WINDOW = timedelta(days=60)


def subject_key(subject: str) -> str:
    stripped = PREFIX.sub("", subject or "")
    return re.sub(r"\s+", " ", stripped).strip().lower()


def contact_of(parsed: Parsed, direction: str) -> str:
    if direction == "in":
        return parsed.from_email
    return parsed.to_emails[0] if parsed.to_emails else ""


def choose_thread(
    conn: sqlite3.Connection, mailbox_id: int, parsed: Parsed, direction: str, now: datetime
) -> int | None:
    for mid in (parsed.in_reply_to, *parsed.references):
        if mid:
            found = repo.thread_of_message_id(conn, mailbox_id, mid)
            if found is not None:
                return found
    if direction == "in":
        found = _assigned_reply(conn, mailbox_id, parsed)
        if found is not None:
            return found
    since = (now - WINDOW).isoformat()
    return repo.find_thread_by_key(
        conn, mailbox_id, subject_key(parsed.subject), contact_of(parsed, direction), since
    )


def _assigned_reply(conn: sqlite3.Connection, mailbox_id: int, parsed: Parsed) -> int | None:
    """Correlate a customer's reply to an accepted owner's recorded outbound.

    Headers alone do not grant access: require a recorded send, matching customer,
    and an accepted assignment to this receiving mailbox. Never merge by subject
    across mailboxes. Ambiguous references remain separate for human review.
    """
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='followup'"
    ).fetchone():
        return None
    candidates = set()
    for mid in {parsed.in_reply_to, *parsed.references} - {""}:
        rows = conn.execute(
            "SELECT DISTINCT t.id FROM outbound o "
            "JOIN message m ON m.id=o.message_pk "
            "JOIN thread t ON t.id=o.thread_id "
            "JOIN followup f ON f.thread_id=t.id "
            "JOIN mailbox receiving ON receiving.id=? "
            "WHERE m.message_id=? AND m.direction='out' "
            "AND lower(m.from_email)=lower(receiving.address) "
            "AND lower(o.sent_by)=lower(receiving.address) "
            "AND lower(f.owner)=lower(receiving.address) "
            "AND lower(t.contact_email)=lower(?)",
            (mailbox_id, mid, parsed.from_email),
        ).fetchall()
        candidates.update(int(row[0]) for row in rows)
    return next(iter(candidates)) if len(candidates) == 1 else None
