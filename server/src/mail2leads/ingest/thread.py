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
    since = (now - WINDOW).isoformat()
    return repo.find_thread_by_key(
        conn, mailbox_id, subject_key(parsed.subject), contact_of(parsed, direction), since
    )
