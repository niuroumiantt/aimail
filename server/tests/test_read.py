"""攻击读数落库:署名、失败显形、不是询盘归 invalid、不挡收信。"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from conftest import make_raw
from mail2leads import backends
from mail2leads.ingest.run import ingest_once, store_raw
from mail2leads.store import repo
from mail2leads.tasks.read import read_message, unread_incoming

NOW = datetime(2026, 9, 19, tzinfo=UTC)
GOOD = {
    "is_inquiry": True,
    "detected_language": "en",
    "summary_zh": "客户要 48 台。",
    "summary_en": "Customer needs 48 units.",
    "facts": ["48 台"],
    "quoted_numbers": ["48"],
}


@pytest.fixture(autouse=True)
def _local(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL", "fast")


def _answer(monkeypatch, payload: dict | str):
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    monkeypatch.setattr(backends, "_call_local", lambda s, u, h: text)


def _incoming(conn, mailbox, **kw) -> int:
    pk, _ = store_raw(conn, mailbox, make_raw(**kw), "in", NOW)
    assert pk is not None
    return pk


def test_reading_is_stored_with_attribution(conn, mailbox, monkeypatch):
    _answer(monkeypatch, GOOD)
    pk = _incoming(conn, mailbox, body="We need 48 units.")
    assert read_message(conn, pk, NOW) == "ok"
    row = repo.latest_reading(conn, pk)
    assert row["model"] == "Spark · fast"
    assert row["task_version"] == "summarize_inquiry@1"
    assert row["produced_at"] == "2026-09-19T00:00:00+00:00"
    assert json.loads(row["payload"])["unverified"] == []


def test_unverified_numbers_are_recorded_not_hidden(conn, mailbox, monkeypatch):
    _answer(monkeypatch, {**GOOD, "quoted_numbers": ["48", "9999"]})
    pk = _incoming(conn, mailbox, body="We need 48 units.")
    read_message(conn, pk, NOW)
    assert json.loads(repo.latest_reading(conn, pk)["payload"])["unverified"] == ["9999"]


def test_failed_reading_is_stored_as_failed_not_empty(conn, mailbox, monkeypatch):
    _answer(monkeypatch, "服务器繁忙")
    pk = _incoming(conn, mailbox)
    assert read_message(conn, pk, NOW) == "failed"
    row = repo.latest_reading(conn, pk)
    assert row["status"] == "failed" and "合规" in row["reason"]
    assert row["model"] == "Spark · fast"


def test_non_inquiry_moves_thread_to_invalid(conn, mailbox, monkeypatch):
    _answer(monkeypatch, {**GOOD, "is_inquiry": False, "quoted_numbers": []})
    pk = _incoming(conn, mailbox, body="Unsubscribe me")
    read_message(conn, pk, NOW)
    assert conn.execute("SELECT folder FROM thread").fetchone()[0] == "invalid"


def test_inquiry_keeps_thread_in_inbox(conn, mailbox, monkeypatch):
    _answer(monkeypatch, GOOD)
    pk = _incoming(conn, mailbox, body="We need 48 units.")
    read_message(conn, pk, NOW)
    assert conn.execute("SELECT folder FROM thread").fetchone()[0] == "inbox"


def test_quoted_history_is_part_of_the_verified_source(conn, mailbox, monkeypatch):
    """模型看到了引用历史,引用里的数字就不算编造——核对依据和模型输入是同一份文本。"""
    _answer(monkeypatch, {**GOOD, "quoted_numbers": ["4850"]})
    pk = _incoming(conn, mailbox, body="Still available?\n\nOn x wrote:\n> Unit price: USD 4,850")
    read_message(conn, pk, NOW)
    assert json.loads(repo.latest_reading(conn, pk)["payload"])["unverified"] == []


class _Source:
    def __init__(self, messages):
        self.messages = messages

    def uid_validity(self):
        return 1

    def new_uids(self, since):
        return sorted(u for u in self.messages if u > since)

    def fetch_raw(self, uid):
        return self.messages[uid]


def test_ingest_reads_incoming_only(conn, mailbox, monkeypatch):
    _answer(monkeypatch, GOOD)
    read: list[int] = []
    reader = lambda c, pk: read.append(pk)  # noqa: E731
    ingest_once(
        conn, mailbox, _Source({1: make_raw(message_id="<1@x>")}), "INBOX", "in", NOW, reader=reader
    )
    ingest_once(
        conn,
        mailbox,
        _Source(
            {1: make_raw(message_id="<2@x>", from_="Sales <sales@example.test>", to="a@b.test")}
        ),
        "Sent",
        "out",
        NOW,
        reader=reader,
    )
    assert len(read) == 1


def test_reader_failure_does_not_block_ingest(conn, mailbox):
    def boom(conn, pk):
        raise RuntimeError("模型挂了")

    report = ingest_once(
        conn,
        mailbox,
        _Source({1: make_raw(message_id="<1@x>"), 2: make_raw(message_id="<2@x>")}),
        "INBOX",
        "in",
        NOW,
        reader=boom,
    )
    assert report.stored == 2
    assert repo.get_cursor(conn, mailbox, "INBOX") == (1, 2)


def test_unread_incoming_lists_only_messages_without_reading(conn, mailbox, monkeypatch):
    _answer(monkeypatch, GOOD)
    a = _incoming(conn, mailbox, message_id="<1@x>")
    b = _incoming(conn, mailbox, message_id="<2@x>")
    read_message(conn, a, NOW)
    assert unread_incoming(conn, mailbox) == [b]


def test_api_exposes_reading_in_the_web_shape(conn, mailbox, monkeypatch):
    from fastapi.testclient import TestClient

    from mail2leads.api.app import create_app

    _answer(monkeypatch, {**GOOD, "quoted_numbers": ["48", "77"]})
    pk = _incoming(conn, mailbox, body="We need 48 units.")
    read_message(conn, pk, NOW)
    thread = TestClient(create_app(conn, mailbox)).get("/api/threads").json()[0]
    r = thread["reading"]
    assert r["status"] == "ok" and r["model"] == "Spark · fast"
    assert r["unverified"] == ["77"] and r["summary_zh"] == "客户要 48 台。"
    assert set(r) >= {
        "is_inquiry",
        "language",
        "facts",
        "quoted_numbers",
        "task_version",
        "produced_at",
    }
