"""攻击宪法第二条:对客户说话的只能是人。没有令牌发不了;后台模块连发信都 import 不到。"""

from __future__ import annotations

import email
import json
from datetime import UTC, datetime
from email import policy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import make_raw
from mail2leads import backends, send
from mail2leads.api.app import create_app
from mail2leads.ingest import run as ingest_run
from mail2leads.ingest.run import store_raw
from mail2leads.tasks import draft as draft_mod
from mail2leads.tasks import read as read_mod

# 来信日期放在过去:回信的 Date 是真实的"现在",线程排序要靠它落在来信之后
NOW = datetime(2026, 9, 1, 8, 12, tzinfo=UTC)


class FakeTransport:
    def __init__(self) -> None:
        self.sent: list[tuple[str, list[str], bytes]] = []

    def deliver(self, sender, recipients, raw):
        self.sent.append((sender, recipients, raw))
        return "ok"


def _thread(conn, mailbox) -> int:
    pk, _ = store_raw(
        conn,
        mailbox,
        make_raw(
            message_id="<q1@aurora.test>", subject="RFQ 2U", body="We need 48 units.", date=NOW
        ),
        "in",
        NOW,
    )
    return int(conn.execute("SELECT thread_id FROM message WHERE id = ?", (pk,)).fetchone()[0])


# ── 令牌 ──


def test_token_is_bound_and_single_use():
    box = send.TokenBox()
    t = box.mint(7, "Larry", now=1000.0)
    with pytest.raises(PermissionError):
        box.consume(t.value, 8, "Larry", now=1001.0)  # 换线程:作废
    t = box.mint(7, "Larry", now=1000.0)
    with pytest.raises(PermissionError):
        box.consume(t.value, 7, "Someone", now=1001.0)  # 换人:作废
    t = box.mint(7, "Larry", now=1000.0)
    assert box.consume(t.value, 7, "Larry", now=1001.0).user == "Larry"
    with pytest.raises(PermissionError):
        box.consume(t.value, 7, "Larry", now=1002.0)  # 用第二次:作废


def test_expired_token_is_rejected():
    box = send.TokenBox()
    t = box.mint(7, "Larry", now=1000.0)
    with pytest.raises(PermissionError, match="过期"):
        box.consume(t.value, 7, "Larry", now=1000.0 + send.TOKEN_TTL_SECONDS + 1)


def test_token_is_only_minted_for_a_person():
    with pytest.raises(PermissionError):
        send.TokenBox().mint(7, "  ")


# ── 发送 ──


def test_send_without_a_token_is_impossible(conn, mailbox):
    tid = _thread(conn, mailbox)
    with pytest.raises(PermissionError):
        send.send(
            conn,
            token=None,
            mailbox_id=mailbox,
            sender="sales@example.test",
            sender_name="",
            thread_id=tid,  # type: ignore[arg-type]
            to=["a@b.test"],
            subject="Re",
            body="hi",
            transport=FakeTransport(),
        )
    other = send.TokenBox().mint(tid + 1, "Larry")
    with pytest.raises(PermissionError):
        send.send(
            conn,
            token=other,
            mailbox_id=mailbox,
            sender="sales@example.test",
            sender_name="",
            thread_id=tid,
            to=["a@b.test"],
            subject="Re",
            body="hi",
            transport=FakeTransport(),
        )


def test_sent_message_threads_correctly_and_lands_as_outgoing(conn, mailbox):
    tid = _thread(conn, mailbox)
    transport = FakeTransport()
    token = send.TokenBox().mint(tid, "Larry")
    send.send(
        conn,
        token=token,
        mailbox_id=mailbox,
        sender="sales@example.test",
        sender_name="Glocal Sales",
        thread_id=tid,
        to=["mikko@aurora.test"],
        subject="Re: RFQ 2U",
        body="Received, thanks. [姓名]",
        transport=transport,
        now=NOW,
    )
    assert len(transport.sent) == 1
    sender, recipients, raw = transport.sent[0]
    assert sender == "sales@example.test" and recipients == ["mikko@aurora.test"]
    msg = email.message_from_bytes(raw, policy=policy.default)
    assert msg["In-Reply-To"] == "<q1@aurora.test>"
    assert "<q1@aurora.test>" in msg["References"]
    rows = conn.execute(
        "SELECT direction, body_new FROM message WHERE thread_id = ? ORDER BY id", (tid,)
    ).fetchall()
    assert [r["direction"] for r in rows] == ["in", "out"]
    assert rows[1]["body_new"].startswith("Received, thanks.")
    assert conn.execute("SELECT folder FROM thread WHERE id = ?", (tid,)).fetchone()[0] == "replied"
    outbound = conn.execute("SELECT sent_by, transport_result FROM outbound").fetchone()
    assert outbound["sent_by"] == "Larry" and outbound["transport_result"] == "ok"


def test_empty_body_or_no_recipient_is_refused(conn, mailbox):
    tid = _thread(conn, mailbox)
    token = send.TokenBox().mint(tid, "Larry")
    with pytest.raises(ValueError):
        send.send(
            conn,
            token=token,
            mailbox_id=mailbox,
            sender="s@x.test",
            sender_name="",
            thread_id=tid,
            to=[],
            subject="Re",
            body="hi",
            transport=FakeTransport(),
        )


def test_background_modules_never_import_send():
    """收信、读数、起草都碰不到发信模块。"""
    for module in (ingest_run, read_mod, draft_mod):
        source = Path(module.__file__).read_text("utf-8")
        assert "mail2leads.send" not in source and "import send" not in source, module.__name__


# ── 起草 ──

DRAFT = {
    "language": "en",
    "subject": "Re: RFQ 2U",
    "body": "Thanks for your inquiry for 48 units of 2U servers. "
    "Could you confirm the delivery address? [姓名]",
    "open_questions": ["delivery address"],
    "quoted_numbers": ["48", "2U"],
}


@pytest.fixture(autouse=True)
def _local(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL", "fast")


def test_draft_is_stored_with_attribution(conn, mailbox, monkeypatch):
    monkeypatch.setattr(backends, "_call_local", lambda s, u, h: json.dumps(DRAFT))
    tid = _thread(conn, mailbox)
    draft_mod.make_draft(conn, tid, NOW)
    row = draft_mod.latest_draft(conn, tid)
    assert (
        row["model"] == "Spark · fast"
        and row["task_version"] == "draft_reply@3"
        and row["status"] == "ok"
    )
    assert json.loads(row["payload"])["unverified"] == []


def test_failed_draft_is_visible_not_blank(conn, mailbox, monkeypatch):
    monkeypatch.setattr(backends, "_call_local", lambda s, u, h: "不给 JSON")
    tid = _thread(conn, mailbox)
    draft_mod.make_draft(conn, tid, NOW)
    row = draft_mod.latest_draft(conn, tid)
    assert row["status"] == "failed" and row["reason"]


def test_draft_source_is_the_whole_thread(conn, mailbox):
    tid = _thread(conn, mailbox)
    store_raw(
        conn,
        mailbox,
        make_raw(
            message_id="<q2@aurora.test>",
            subject="Re: RFQ 2U",
            in_reply_to="<q1@aurora.test>",
            body="Also need rails.",
            date=NOW,
        ),
        "in",
        NOW,
    )
    source_id, text = draft_mod.thread_source(conn, tid)
    assert "We need 48 units." in text and "Also need rails." in text
    assert source_id == int(
        conn.execute("SELECT id FROM message WHERE message_id = '<q2@aurora.test>'").fetchone()[0]
    )


# ── API ──


def test_api_send_flow_requires_person_token_and_transport(conn, mailbox):
    tid = _thread(conn, mailbox)
    no_smtp = TestClient(create_app(conn, mailbox))
    assert no_smtp.post(f"/api/threads/{tid}/send-token").status_code == 401
    ok_token = no_smtp.post(f"/api/threads/{tid}/send-token", headers={"X-User": "Larry"}).json()[
        "token"
    ]
    body = {"token": ok_token, "to": ["mikko@aurora.test"], "subject": "Re", "body": "hi"}
    assert (
        no_smtp.post(f"/api/threads/{tid}/send", json=body, headers={"X-User": "Larry"}).status_code
        == 503
    )

    transport = FakeTransport()
    client = TestClient(create_app(conn, mailbox, sender="sales@example.test", transport=transport))
    bad = client.post(
        f"/api/threads/{tid}/send", json={**body, "token": "forged"}, headers={"X-User": "Larry"}
    )
    assert bad.status_code == 403 and transport.sent == []
    token = client.post(f"/api/threads/{tid}/send-token", headers={"X-User": "Larry"}).json()[
        "token"
    ]
    sent = client.post(
        f"/api/threads/{tid}/send", json={**body, "token": token}, headers={"X-User": "Larry"}
    )
    assert sent.status_code == 200 and len(transport.sent) == 1
    assert [m["direction"] for m in sent.json()["messages"]] == ["in", "out"]
    again = client.post(
        f"/api/threads/{tid}/send", json={**body, "token": token}, headers={"X-User": "Larry"}
    )
    assert again.status_code == 403 and len(transport.sent) == 1


def test_api_draft_endpoints(conn, mailbox, monkeypatch):
    monkeypatch.setattr(backends, "_call_local", lambda s, u, h: json.dumps(DRAFT))
    tid = _thread(conn, mailbox)
    client = TestClient(create_app(conn, mailbox))
    assert client.get(f"/api/threads/{tid}/draft").json() == {"draft": None}
    assert client.post(f"/api/threads/{tid}/draft").status_code == 401
    made = client.post(f"/api/threads/{tid}/draft", headers={"X-User": "Larry"}).json()["draft"]
    assert (
        made["status"] == "ok"
        and made["body"].startswith("Thanks")
        and made["model"] == "Spark · fast"
    )
    assert client.get(f"/api/threads/{tid}/draft").json()["draft"]["id"] == made["id"]
