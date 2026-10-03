"""交接后的个人来信必须保留会话归属、邮件隔离和发送核对能力。"""

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from aimail import backends, send
from aimail.api.app import create_app
from aimail.ingest.run import store_raw
from aimail.send.accounts import SendingAccount
from aimail.store import followup, repo
from aimail.tasks.read import read_message
from conftest import make_raw

NOW = datetime(2026, 10, 3, tzinfo=UTC)
OWNER = "owner@example.test"


class Transport:
    def __init__(self):
        self.calls = []
        self.uncertain = False

    def deliver(self, sender, recipients, raw):
        self.calls.append(raw)
        if self.uncertain:
            raise TimeoutError("controlled unknown result")
        return "ok"


@pytest.fixture
def conversation(conn, mailbox):
    personal = repo.ensure_mailbox(conn, OWNER)
    pk, _ = store_raw(conn, mailbox, make_raw(body="Please quote 48 units."), "in", NOW)
    tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    followup.init(conn)
    followup.transfer(conn, tid, "sales@example.test", OWNER, 0, {}, "")
    followup.decide(conn, tid, OWNER, 1, "accept")
    transport = Transport()
    send.send(
        conn,
        token=send.TokenBox().mint(tid, OWNER),
        mailbox_id=mailbox,
        sender=OWNER,
        sender_name="Owner",
        thread_id=tid,
        to=["mikko@aurora.test"],
        subject="Re: RFQ",
        body="Acknowledged by owner.",
        transport=transport,
        now=NOW,
    )
    outgoing = conn.execute(
        "SELECT message_id FROM message WHERE thread_id=? AND direction='out'",
        (tid,),
    ).fetchone()[0]
    reply, _ = store_raw(
        conn,
        personal,
        make_raw(
            message_id="<personal-reply@aurora.test>",
            to=OWNER,
            in_reply_to=outgoing,
            body="Please confirm 48 units.",
        ),
        "in",
        NOW,
    )
    assert conn.execute("SELECT thread_id FROM message WHERE id=?", (reply,)).fetchone()[0] == tid
    return tid, reply, personal, transport


@pytest.mark.parametrize("failure", [False, True])
def test_cross_mailbox_reading_preserves_source_and_does_not_expand_history(
    conn,
    mailbox,
    conversation,
    monkeypatch,
    failure,
):
    tid, reply, personal, _ = conversation
    for box, marker in [(mailbox, "SHARED_PRIVATE"), (personal, "PERSONAL_PRIVATE")]:
        store_raw(
            conn,
            box,
            make_raw(message_id=f"<{marker}@aurora.test>", subject=marker, body=marker),
            "in",
            NOW,
            new_thread=True,
        )
    seen = []

    def complete(*args):
        seen.append(args[1])
        if failure:
            raise backends.LLMError("controlled model failure")
        return json.dumps(
            {
                "is_inquiry": False,
                "detected_language": "en",
                "summary_zh": "确认48件",
                "summary_en": "Confirm 48 units",
                "facts": ["48 units"],
                "quoted_numbers": ["48"],
            }
        )

    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL", "test")
    monkeypatch.setattr(backends, "_call_local", complete)
    assert read_message(conn, reply, NOW) == ("failed" if failure else "ok")
    assert "48 units" in seen[0]
    assert "SHARED_PRIVATE" not in seen[0] and "PERSONAL_PRIVATE" not in seen[0]
    reading = repo.latest_reading(conn, reply)
    assert reading["status"] == ("failed" if failure else "ok")
    assert reading["source_id"] == reply
    source = conn.execute(
        "SELECT mailbox_id,thread_id FROM message WHERE id=?", (reply,)
    ).fetchone()
    assert tuple(source) == (personal, tid)


def test_cross_mailbox_analyze_request_stores_reading(conn, mailbox, conversation, monkeypatch):
    tid, reply, _, _ = conversation
    monkeypatch.setattr(backends, "ready", lambda: (True, ""))
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL", "test")
    monkeypatch.setattr(
        backends,
        "_call_local",
        lambda *args: json.dumps(
            {
                "is_inquiry": False,
                "detected_language": "en",
                "summary_zh": "确认48件",
                "summary_en": "Confirm 48 units",
                "facts": [],
                "quoted_numbers": ["48"],
            }
        ),
    )
    with TestClient(create_app(conn, mailbox)) as client:
        assert client.post(f"/api/threads/{tid}/analyze").status_code == 200
    assert repo.latest_reading(conn, reply)["status"] == "ok"


@pytest.mark.parametrize("uncertain", [False, True])
def test_personal_reply_stays_in_shared_conversation_and_unknown_send_can_be_resolved(
    conn,
    mailbox,
    conversation,
    uncertain,
):
    tid, reply, personal, transport = conversation
    transport.uncertain = uncertain
    headers = {"X-OA-User": OWNER, "X-OA-Email": OWNER}
    client = TestClient(
        create_app(
            conn,
            mailbox,
            require_oa_auth=True,
            mailbox_access={OWNER: (OWNER,)},
            followup_members=(OWNER,),
            sending_accounts={OWNER: SendingAccount(OWNER, "Owner", transport)},
        )
    )
    token = client.post(f"/api/followups/{tid}/reply-token", headers=headers).json()["token"]
    result = client.post(
        f"/api/followups/{tid}/reply",
        headers=headers,
        json={
            "token": token,
            "subject": "Confirmed specifications",
            "body": "Confirmed by owner.",
        },
    )
    assert result.status_code == (422 if uncertain else 200)
    if uncertain:
        pending = client.get(f"/api/followups/{tid}", headers=headers).json()["unresolved_send"]
        assert client.post(f"/api/followups/{tid}/reply-token", headers=headers).status_code == 409
        resolution = client.post(
            f"/api/followups/{tid}/unresolved/{pending['id']}/resolve",
            headers=headers,
            json={"outcome": "sent", "evidence_reference": "internal provider log 123456"},
        )
        assert resolution.status_code == 200, resolution.text
        assert client.post(f"/api/followups/{tid}/reply-token", headers=headers).status_code == 200
        assert client.post(
            f"/api/followups/{tid}/unresolved/{pending['id']}/resolve",
            headers=headers,
            json={"outcome": "sent", "evidence_reference": "internal provider log 123456"},
        ).json()["already_resolved"]
    latest = conn.execute(
        "SELECT m.thread_id,m.mailbox_id,m.in_reply_to FROM outbound o "
        "JOIN message m ON m.id=o.message_pk ORDER BY o.id DESC LIMIT 1"
    ).fetchone()
    assert tuple(latest) == (tid, mailbox, "<personal-reply@aurora.test>")
    assert len(transport.calls) == 2  # 核对和重试核对不会再次调用SMTP。
    assert (
        conn.execute("SELECT mailbox_id FROM message WHERE id=?", (reply,)).fetchone()[0]
        == personal
    )
