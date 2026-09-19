"""攻击归并:靠头归并、靠主题+对方归并、不该归并的不归并。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from conftest import make_raw
from mail2leads.ingest.run import store_raw
from mail2leads.ingest.thread import subject_key

NOW = datetime(2026, 9, 19, tzinfo=UTC)


def _thread_of(conn, pk: int) -> int:
    return int(conn.execute("SELECT thread_id FROM message WHERE id = ?", (pk,)).fetchone()[0])


def test_reply_with_in_reply_to_joins_thread(conn, mailbox):
    a, _ = store_raw(conn, mailbox, make_raw(message_id="<m1@x.test>", subject="RFQ 2U"), "in", NOW)
    b, _ = store_raw(
        conn,
        mailbox,
        make_raw(
            message_id="<m2@x.test>",
            subject="totally different subject",
            in_reply_to="<m1@x.test>",
            from_="Other Person <other@else.test>",
        ),
        "in",
        NOW,
    )
    assert _thread_of(conn, a) == _thread_of(conn, b)


def test_reply_with_references_only_joins_thread(conn, mailbox):
    a, _ = store_raw(conn, mailbox, make_raw(message_id="<m1@x.test>"), "in", NOW)
    b, _ = store_raw(
        conn,
        mailbox,
        make_raw(message_id="<m3@x.test>", references="<m0@x.test> <m1@x.test>"),
        "in",
        NOW,
    )
    assert _thread_of(conn, a) == _thread_of(conn, b)


def test_same_subject_same_sender_joins_thread(conn, mailbox):
    a, _ = store_raw(
        conn, mailbox, make_raw(message_id="<m1@x.test>", subject="RFQ 2U servers"), "in", NOW
    )
    b, _ = store_raw(
        conn, mailbox, make_raw(message_id="<m2@x.test>", subject="Re: RFQ 2U servers"), "in", NOW
    )
    assert _thread_of(conn, a) == _thread_of(conn, b)


def test_same_subject_different_sender_is_a_new_thread(conn, mailbox):
    """两个客户都发「RFQ」,不能并成一条。"""
    a, _ = store_raw(conn, mailbox, make_raw(message_id="<m1@x.test>", subject="RFQ"), "in", NOW)
    b, _ = store_raw(
        conn,
        mailbox,
        make_raw(message_id="<m2@y.test>", subject="RFQ", from_="Other <o@y.test>"),
        "in",
        NOW,
    )
    assert _thread_of(conn, a) != _thread_of(conn, b)


def test_same_subject_after_window_is_a_new_thread(conn, mailbox):
    a, _ = store_raw(
        conn,
        mailbox,
        make_raw(message_id="<m1@x.test>", subject="RFQ", date=NOW - timedelta(days=90)),
        "in",
        NOW - timedelta(days=90),
    )
    b, _ = store_raw(conn, mailbox, make_raw(message_id="<m2@x.test>", subject="RFQ"), "in", NOW)
    assert _thread_of(conn, a) != _thread_of(conn, b)


def test_prefixes_are_normalized():
    assert subject_key("Re: RE: Fwd: 回复:  RFQ  2U") == "rfq 2u"
    assert subject_key("答复: 询价") == "询价"
    assert subject_key("plain") == "plain"


def test_outgoing_reply_joins_customer_thread(conn, mailbox):
    """我方从 Sent 收进来的回信要归到客户那条线程,对方是收件人。"""
    a, _ = store_raw(conn, mailbox, make_raw(message_id="<m1@x.test>", subject="RFQ 2U"), "in", NOW)
    b, _ = store_raw(
        conn,
        mailbox,
        make_raw(
            message_id="<r1@example.test>",
            subject="Re: RFQ 2U",
            from_="Sales <sales@example.test>",
            to="mikko@aurora.test",
        ),
        "out",
        NOW,
    )
    assert _thread_of(conn, a) == _thread_of(conn, b)
    assert conn.execute("SELECT direction FROM message WHERE id = ?", (b,)).fetchone()[0] == "out"
