"""一次收信:拉新 UID → 原文先落库 → 解析 → 切引用 → 归并线程。

顺序是刻意的:原文先于一切。解析炸了,原文也已经在库里,主题写「(无法解析的邮件)」。
每存一封就推进游标,中途断了下次从断点继续;重复投递靠 Message-ID 和原文哈希两道唯一约束挡住。
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from mail2leads.ingest import attachments, quote, thread
from mail2leads.ingest.imap import Source
from mail2leads.ingest.parse import Parsed, parse
from mail2leads.store import repo

log = logging.getLogger("mail2leads.ingest")


@dataclass
class Report:
    fetched: int = 0
    stored: int = 0
    skipped: int = 0
    unparsable: int = 0


def _fallback(raw: bytes) -> Parsed:
    return Parsed(
        message_id=f"sha256:{hashlib.sha256(raw).hexdigest()}",
        in_reply_to="",
        references=(),
        subject="(无法解析的邮件)",
        from_name="",
        from_email="unknown@unparsable.invalid",
        to_emails=(),
        sent_at="",
        text=raw.decode("utf-8", errors="replace")[:4000],
        attachments=(),
    )


def store_raw(
    conn: sqlite3.Connection,
    mailbox_id: int,
    raw: bytes,
    direction: str,
    now: datetime,
    *,
    new_thread: bool = False,
) -> tuple[int | None, bool]:
    """落一封。返回 (message 主键或 None, 是否解析失败)。已存在的返回 (None, False)。"""
    if repo.raw_seen(conn, hashlib.sha256(raw).hexdigest()):
        return None, False
    unparsable = False
    try:
        parsed = parse(raw)
    except Exception:  # noqa: BLE001 —— 任何解析异常都不能丢原文
        log.exception("解析失败,原文照存")
        parsed = _fallback(raw)
        unparsable = True
    if repo.thread_of_message_id(conn, mailbox_id, parsed.message_id) is not None:
        return None, False

    received = now.replace(microsecond=0).isoformat()
    at = parsed.sent_at or received
    body_new, body_quoted = quote.split(parsed.text)

    conn.execute("BEGIN")
    try:
        thread_id = (
            None if new_thread else thread.choose_thread(conn, mailbox_id, parsed, direction, now)
        )
        if thread_id is None:
            thread_id = repo.create_thread(
                conn,
                mailbox_id,
                parsed.subject or "(无主题)",
                thread.subject_key(parsed.subject),
                thread.contact_of(parsed, direction),
                parsed.from_name if direction == "in" else "",
                at,
            )
        pk = repo.insert_message(
            conn, mailbox_id, thread_id, parsed, direction, raw, body_new, body_quoted, received
        )
        repo.touch_thread(conn, thread_id, at)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return pk, unparsable


def ingest_once(
    conn: sqlite3.Connection,
    mailbox_id: int,
    source: Source,
    folder: str,
    direction: str = "in",
    now: datetime | None = None,
    reader: Callable[[sqlite3.Connection, int], object] | None = None,
) -> Report:
    """reader 是可选的读数钩子:来信落库后立刻调;它炸了只记日志,收信不能因此停。"""
    now = now or datetime.now(UTC)
    report = Report()
    validity = source.uid_validity()
    cursor = repo.get_cursor(conn, mailbox_id, folder)
    last_uid = cursor[1] if cursor and cursor[0] == validity else 0
    if cursor and cursor[0] != validity:
        log.warning(
            "UIDVALIDITY 变了(%s → %s),从头再拉;重复的会被唯一约束挡住", cursor[0], validity
        )

    for uid in source.new_uids(last_uid):
        raw = source.fetch_raw(uid)
        report.fetched += 1
        pk, unparsable = store_raw(conn, mailbox_id, raw, direction, now)
        if pk is None:
            report.skipped += 1
        else:
            report.stored += 1
            report.unparsable += int(unparsable)
            try:
                attachments.extract_for_message(conn, pk, now)
            except Exception:  # noqa: BLE001 —— 附件读不出只记日志,收信不能因此停
                log.exception("读附件失败 message=%s", pk)
            if reader is not None and direction == "in":
                try:
                    reader(conn, pk)
                except Exception:  # noqa: BLE001 —— 读数失败不能挡住收信
                    log.exception("读数失败 message=%s", pk)
        repo.set_cursor(conn, mailbox_id, folder, validity, uid)
    return report
