import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from aimail.api.app import create_app
from aimail.ingest.run import store_raw
from aimail.send.accounts import SendingAccount, from_env
from aimail.store import repo
from conftest import make_raw


class RecordingTransport:
    def __init__(self):
        self.sent = []

    def deliver(self, sender, recipients, raw):
        self.sent.append(sender)
        return "ok"


def test_accounts_reference_secrets_and_fail_without_echoing_them():
    item = {
        "address": "cloud@glocalstorage.com",
        "host": "smtp.example.test",
        "password_env": "CLOUD_SMTP_PASSWORD",
    }
    accounts = from_env(
        {"SENDING_ACCOUNTS": json.dumps([item]), "CLOUD_SMTP_PASSWORD": "private-value"}
    )
    assert accounts[item["address"]].transport.user == item["address"]
    with pytest.raises(ValueError) as error:
        from_env({"SENDING_ACCOUNTS": json.dumps([item])})
    assert "private-value" not in str(error.value)
    item["address"] = "sales@glocalstorage.com"
    with pytest.raises(ValueError):
        from_env({"SENDING_ACCOUNTS": json.dumps([item]), "CLOUD_SMTP_PASSWORD": "private-value"})


def test_authenticated_employee_selects_own_transport_not_request_sender(conn):
    box = repo.ensure_mailbox(conn, "sales@glocalstorage.com")
    pk, _ = store_raw(conn, box, make_raw(), "in", datetime.now(UTC))
    tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    larry, cloud = "larry@glocalstorage.com", "cloud@glocalstorage.com"
    lt, ct = RecordingTransport(), RecordingTransport()
    app = TestClient(
        create_app(
            conn,
            box,
            sender=larry,
            transport=lt,
            require_oa_auth=True,
            mailbox_access={cloud: ("sales@glocalstorage.com",)},
            sending_accounts={cloud: SendingAccount(cloud, "Cloud", ct)},
        )
    )
    headers = {"X-OA-User": "cloud", "X-OA-Email": cloud}
    token = app.post(f"/api/threads/{tid}/send-token", headers=headers).json()["token"]
    result = app.post(
        f"/api/threads/{tid}/send",
        headers=headers,
        json={
            "token": token,
            "to": ["customer@example.test"],
            "subject": "Re: RFQ",
            "body": "Hello",
            "sender": larry,
        },
    )
    assert result.status_code == 200
    assert ct.sent == [cloud]
    assert lt.sent == []


def test_only_accepted_owner_can_reply_to_shared_conversation(conn):
    from aimail.store import followup

    box = repo.ensure_mailbox(conn, "sales@glocalstorage.com")
    pk, _ = store_raw(conn, box, make_raw(), "in", datetime.now(UTC))
    tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    larry, cloud = "larry@glocalstorage.com", "cloud@glocalstorage.com"
    ct = RecordingTransport()
    app = TestClient(
        create_app(
            conn,
            box,
            sender=larry,
            require_oa_auth=True,
            mailbox_access={larry: ("sales@glocalstorage.com",)},
            followup_members=(larry, cloud),
            sending_accounts={cloud: SendingAccount(cloud, "Cloud", ct)},
        )
    )
    followup.transfer(conn, tid, larry, cloud, 0, {}, "")
    headers = {"X-OA-User": "cloud", "X-OA-Email": cloud}
    assert app.post(f"/api/followups/{tid}/reply-token", headers=headers).status_code == 403
    followup.decide(conn, tid, cloud, 1, "accept")
    token = app.post(f"/api/followups/{tid}/reply-token", headers=headers).json()["token"]
    payload = {"token": token, "subject": "Re: RFQ", "body": "Hello"}
    assert app.post(f"/api/followups/{tid}/reply", headers=headers, json=payload).status_code == 200
    assert app.post(f"/api/followups/{tid}/reply", headers=headers, json=payload).status_code == 403
    assert ct.sent == [cloud]
    assert app.get("/api/threads", headers=headers).status_code == 403
    original = {"X-OA-User": "admin", "X-OA-Email": larry}
    assert app.get(f"/api/threads/{tid}", headers=original).status_code == 200
    assert app.post(f"/api/threads/{tid}/send-token", headers=original).status_code == 403
    # A token minted before transfer cannot bypass the current-owner check either.
    assert (
        app.post(
            f"/api/threads/{tid}/send",
            headers=original,
            json={
                "token": "stale-token",
                "to": ["customer@example.test"],
                "subject": "Re: RFQ",
                "body": "Hello",
            },
        ).status_code
        == 403
    )
