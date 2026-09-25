"""攻击收信:幂等、断点续拉、UIDVALIDITY 变化、解析失败不丢原文。"""

from __future__ import annotations

from datetime import UTC, datetime

from aimail.ingest.run import ingest_once
from aimail.store import repo
from conftest import make_raw

NOW = datetime(2026, 9, 19, tzinfo=UTC)


class FakeSource:
    def __init__(self, messages: dict[int, bytes], validity: int = 1) -> None:
        self.messages = messages
        self.validity = validity
        self.fetched: list[int] = []

    def uid_validity(self) -> int:
        return self.validity

    def new_uids(self, since_uid: int) -> list[int]:
        return sorted(u for u in self.messages if u > since_uid)

    def fetch_raw(self, uid: int) -> bytes:
        self.fetched.append(uid)
        return self.messages[uid]


def test_first_run_stores_everything_and_advances_cursor(conn, mailbox):
    src = FakeSource(
        {
            1: make_raw(message_id="<1@x>"),
            2: make_raw(message_id="<2@x>", subject="B", from_="b@y.test"),
        }
    )
    report = ingest_once(conn, mailbox, src, "INBOX", now=NOW)
    assert (report.fetched, report.stored, report.skipped) == (2, 2, 0)
    assert repo.get_cursor(conn, mailbox, "INBOX") == (1, 2)


def test_second_run_fetches_nothing_new(conn, mailbox):
    src = FakeSource({1: make_raw(message_id="<1@x>")})
    ingest_once(conn, mailbox, src, "INBOX", now=NOW)
    report = ingest_once(conn, mailbox, src, "INBOX", now=NOW)
    assert report.fetched == 0
    assert src.fetched == [1]


def test_redelivered_message_is_skipped_not_duplicated(conn, mailbox):
    """服务端重投同一封(新 UID、同 Message-ID):存一次。"""
    raw = make_raw(message_id="<same@x>")
    src = FakeSource({1: raw})
    ingest_once(conn, mailbox, src, "INBOX", now=NOW)
    src.messages[2] = raw
    report = ingest_once(conn, mailbox, src, "INBOX", now=NOW)
    assert (report.fetched, report.stored, report.skipped) == (1, 0, 1)
    assert conn.execute("SELECT COUNT(*) FROM message").fetchone()[0] == 1


def test_uidvalidity_change_refetches_without_duplicating(conn, mailbox):
    src = FakeSource({5: make_raw(message_id="<1@x>")}, validity=1)
    ingest_once(conn, mailbox, src, "INBOX", now=NOW)
    src.validity = 2
    src.messages = {1: make_raw(message_id="<1@x>")}
    report = ingest_once(conn, mailbox, src, "INBOX", now=NOW)
    assert report.fetched == 1 and report.stored == 0
    assert repo.get_cursor(conn, mailbox, "INBOX") == (2, 1)


def test_unparsable_message_keeps_its_raw_bytes(conn, mailbox):
    src = FakeSource({1: b"\xff\xfe garbage \x00"})
    report = ingest_once(conn, mailbox, src, "INBOX", now=NOW)
    assert report.stored == 1
    row = conn.execute("SELECT raw, subject FROM message").fetchone()
    assert bytes(row["raw"]) == b"\xff\xfe garbage \x00"


def test_cursor_advances_per_message_so_a_crash_resumes(conn, mailbox):
    class Explodes(FakeSource):
        def fetch_raw(self, uid: int) -> bytes:
            if uid == 2:
                raise ConnectionError("断了")
            return super().fetch_raw(uid)

    src = Explodes({1: make_raw(message_id="<1@x>"), 2: make_raw(message_id="<2@x>")})
    try:
        ingest_once(conn, mailbox, src, "INBOX", now=NOW)
    except ConnectionError:
        pass
    assert repo.get_cursor(conn, mailbox, "INBOX") == (1, 1)
    assert conn.execute("SELECT COUNT(*) FROM message").fetchone()[0] == 1
