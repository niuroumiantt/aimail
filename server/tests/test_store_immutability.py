"""攻击宪法第三条:原文不可变。数据库层面直接拒绝,不靠代码自觉。"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from conftest import make_raw
from mail2leads.ingest.run import store_raw


def _one(conn, mailbox, **kw) -> int:
    pk, _ = store_raw(conn, mailbox, make_raw(**kw), "in", datetime(2026, 9, 19, tzinfo=UTC))
    assert pk is not None
    return pk


def test_message_update_is_rejected(conn, mailbox):
    pk = _one(conn, mailbox)
    with pytest.raises(sqlite3.IntegrityError, match="原文不可变"):
        conn.execute("UPDATE message SET subject = '改了' WHERE id = ?", (pk,))


def test_message_delete_is_rejected(conn, mailbox):
    pk = _one(conn, mailbox)
    with pytest.raises(sqlite3.IntegrityError, match="原文不可变"):
        conn.execute("DELETE FROM message WHERE id = ?", (pk,))


def test_attachment_is_immutable(conn, mailbox):
    _one(conn, mailbox, attachments=[("spec.pdf", b"%PDF-1.4 fake", "application/pdf")])
    with pytest.raises(sqlite3.IntegrityError, match="原文不可变"):
        conn.execute("UPDATE attachment SET filename = 'x' ")
    with pytest.raises(sqlite3.IntegrityError, match="原文不可变"):
        conn.execute("DELETE FROM attachment")


def test_same_message_id_is_stored_once(conn, mailbox):
    now = datetime(2026, 9, 19, tzinfo=UTC)
    raw1 = make_raw(message_id="<dup@x.test>", body="first")
    raw2 = make_raw(message_id="<dup@x.test>", body="second delivery, different bytes")
    assert store_raw(conn, mailbox, raw1, "in", now)[0] is not None
    assert store_raw(conn, mailbox, raw2, "in", now)[0] is None
    assert conn.execute("SELECT COUNT(*) FROM message").fetchone()[0] == 1


def test_same_bytes_are_stored_once_even_without_message_id(conn, mailbox):
    """没有 Message-ID 的信靠原文哈希判重。"""
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = "no id"
    msg["From"] = "a@b.test"
    msg["To"] = "sales@example.test"
    msg.set_content("body")
    raw = msg.as_bytes()
    now = datetime(2026, 9, 19, tzinfo=UTC)
    assert store_raw(conn, mailbox, raw, "in", now)[0] is not None
    assert store_raw(conn, mailbox, raw, "in", now)[0] is None


def test_raw_bytes_are_kept_verbatim(conn, mailbox):
    raw = make_raw(body="精确到字节")
    pk, _ = store_raw(conn, mailbox, raw, "in", datetime(2026, 9, 19, tzinfo=UTC))
    stored = conn.execute("SELECT raw FROM message WHERE id = ?", (pk,)).fetchone()[0]
    assert bytes(stored) == raw
