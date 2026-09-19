"""攻击 M6:记忆是对不可变记录的一次查询。谁算同一位客户由代码裁决;
模型看到的历史只有原文摘录与我们记的状态,别的模型输出一个字都进不去。"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import make_raw
from mail2leads import backends
from mail2leads.api.app import create_app
from mail2leads.ingest.run import store_raw
from mail2leads.store import history, repo
from mail2leads.tasks import draft as draft_mod
from mail2leads.tasks.read import read_message
from mail2leads.tasks.summarize import compose_source
from mail2leads.verify.numbers import unverified_numbers

JUNE = datetime(2026, 6, 2, 9, 0, tzinfo=UTC)
SEPT = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def _thread(conn, mailbox, *, from_, subject, body, message_id, date, direction="in") -> int:
    raw = make_raw(from_=from_, subject=subject, body=body, message_id=message_id, date=date)
    pk, _ = store_raw(conn, mailbox, raw, direction, date)
    assert pk is not None
    return int(conn.execute("SELECT thread_id FROM message WHERE id = ?", (pk,)).fetchone()[0])


@pytest.fixture
def customer(conn, mailbox):
    """六月一条已成交的线程,九月一句话的新来信。"""
    old = _thread(
        conn,
        mailbox,
        from_="Mikko Laine <mikko@aurora.test>",
        subject="RFQ 20 x R740 servers",
        body="We need 20 × Dell R740 servers, 2× Gold 6130, 256GB. Quote CIF Helsinki.",
        message_id="<june@aurora.test>",
        date=JUNE,
    )
    conn.execute(
        "INSERT INTO lead (mailbox_id, thread_id, company, wants, status, confirmed_by, "
        "confirmed_at, updated_at) VALUES (?, ?, 'Aurora', 'R740', 'won', 'Larry', ?, ?)",
        (mailbox, old, JUNE.isoformat(), JUNE.isoformat()),
    )
    new = _thread(
        conn,
        mailbox,
        from_="Mikko Laine <mikko@aurora.test>",
        subject="Re: our order",
        body="Hi, please add 10 more units, same as last time.",
        message_id="<sept@aurora.test>",
        date=SEPT,
    )
    return old, new


def test_same_address_is_the_same_customer(conn, mailbox, customer):
    old, new = customer
    assert [h.thread_id for h in history.related_threads(conn, mailbox, new)] == [old]


def test_same_company_domain_is_the_same_customer(conn, mailbox, customer):
    old, new = customer
    colleague = _thread(
        conn,
        mailbox,
        from_="Anna Virtanen <anna@aurora.test>",
        subject="Rails for the R740s",
        body="Do you have rail kits for the servers Mikko ordered?",
        message_id="<anna@aurora.test>",
        date=SEPT + timedelta(days=1),
    )
    assert {h.thread_id for h in history.related_threads(conn, mailbox, colleague)} == {old, new}


def test_public_mail_domain_is_not_a_company(conn, mailbox):
    a = _thread(
        conn,
        mailbox,
        from_="A <a@gmail.com>",
        subject="A1",
        body="x",
        message_id="<a1@g>",
        date=JUNE,
    )
    _thread(
        conn,
        mailbox,
        from_="B <b@gmail.com>",
        subject="B1",
        body="y",
        message_id="<b1@g>",
        date=JUNE,
    )
    a2 = _thread(
        conn,
        mailbox,
        from_="A <a@gmail.com>",
        subject="A2",
        body="z",
        message_id="<a2@g>",
        date=SEPT,
    )
    assert [h.thread_id for h in history.related_threads(conn, mailbox, a2)] == [a]
    assert history.company_key("Someone@GMAIL.com") == "someone@gmail.com"
    assert history.company_key("mikko@aurora.test") == "aurora.test"


def test_history_excludes_itself_and_other_mailboxes(conn, mailbox, customer):
    old, new = customer
    other = repo.ensure_mailbox(conn, "other@example.test", "Other")
    elsewhere = _thread(
        conn,
        other,
        from_="Mikko Laine <mikko@aurora.test>",
        subject="Private note",
        body="secret",
        message_id="<private@aurora.test>",
        date=SEPT,
    )
    ids = [h.thread_id for h in history.related_threads(conn, mailbox, new)]
    assert new not in ids and elsewhere not in ids and ids == [old]
    assert history.related_threads(conn, other, elsewhere) == []
    with pytest.raises(KeyError):
        history.related_threads(conn, other, new)  # 别的邮箱连问都问不到


def test_history_is_raw_excerpt_and_our_status_never_a_model_summary(conn, mailbox, customer):
    old, new = customer
    old_pk = conn.execute("SELECT id FROM message WHERE thread_id = ?", (old,)).fetchone()[0]
    conn.execute(
        "INSERT INTO message_reading (source_id, model, task_version, produced_at, status, payload)"
        " VALUES (?, 'Spark · fast', 'summarize_inquiry@2', '2026-06-02T09:01:00+00:00', 'ok', ?)",
        (old_pk, json.dumps({"summary_zh": "HALLUCINATED 999 台"})),
    )
    text = history.for_thread(conn, mailbox, new)
    assert history.HISTORY_HEADER in text
    assert "RFQ 20 x R740 servers" in text and "20 × Dell R740" in text
    assert "成交" in text and "2026-06-02" in text
    assert "HALLUCINATED" not in text and "999" not in text


def test_numbers_from_history_count_as_verified(conn, mailbox, customer):
    _, new = customer
    source = compose_source(
        "Re: our order", "please add 10 more units", history=history.for_thread(conn, mailbox, new)
    )
    assert unverified_numbers(["10", "R740", "20"], source) == ()
    assert unverified_numbers(["R750"], source) == ("R750",)


def test_no_history_adds_nothing_to_the_prompt(conn, mailbox):
    only = _thread(
        conn, mailbox, from_="X <x@x.test>", subject="S", body="b", message_id="<x@x>", date=JUNE
    )
    assert history.for_thread(conn, mailbox, only) == ""
    assert compose_source("S", "b", history="") == "Subject: S\n\nb"


def test_reader_shows_the_model_this_customers_history(conn, mailbox, customer, monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL", "fast")
    seen: list[str] = []

    def fake(system: str, user: str, hint: str) -> str:
        seen.append(user)
        return json.dumps(
            {
                "is_inquiry": True,
                "detected_language": "en",
                "summary_zh": "再加 10 台",
                "summary_en": "10 more",
                "facts": ["再加 10 台 R740(来自此前往来)"],
                "quoted_numbers": ["10", "R740"],
            }
        )

    monkeypatch.setattr(backends, "_call_local", fake)
    _, new = customer
    new_pk = conn.execute("SELECT id FROM message WHERE thread_id = ?", (new,)).fetchone()[0]
    assert read_message(conn, int(new_pk)) == "ok"
    assert history.HISTORY_HEADER in seen[0] and "R740" in seen[0]
    row = repo.latest_reading(conn, int(new_pk))
    assert json.loads(row["payload"])["unverified"] == []  # R740 来自历史,回得到原文


def test_draft_source_carries_history(conn, mailbox, customer):
    _, new = customer
    _, text = draft_mod.thread_source(conn, new)
    assert history.HISTORY_HEADER in text and "R740" in text
    assert text.index("please add 10 more") < text.index(history.HISTORY_HEADER)


def test_thread_detail_carries_history_in_the_web_shape(conn, mailbox, customer):
    old, new = customer
    client = TestClient(create_app(conn, mailbox))
    detail = client.get(f"/api/threads/{new}").json()
    assert [h["id"] for h in detail["history"]] == [str(old)]
    item = detail["history"][0]
    for key in ("subject", "first_at", "last_at", "folder", "replied", "lead_status", "excerpt"):
        assert key in item, key
    assert item["lead_status"] == "won" and item["replied"] is False
    assert client.get(f"/api/threads/{old}").json()["history"][0]["id"] == str(new)
    assert "history" not in client.get("/api/threads").json()[0]  # 列表不算历史,省事
