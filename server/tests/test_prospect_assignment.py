from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import make_raw
from mail2leads import outreach as o
from mail2leads.api.app import create_app
from mail2leads.ingest.run import store_raw
from mail2leads.send.accounts import SendingAccount
from mail2leads.store import followup
from test_outreach import PAYLOAD, STEPS, Transport


def test_personal_approval_requires_accepted_ownership(conn, mailbox):
    owner, recipient = "larry@example.test", "cloud@example.test"
    transport = Transport()
    app = TestClient(
        create_app(
            conn,
            mailbox,
            sender=owner,
            require_oa_auth=True,
            outreach_approval_proxy_key="test-approval",
            followup_members=(owner, recipient),
            sending_accounts={recipient: SendingAccount(recipient, "Cloud", transport)},
        )
    )
    sid = o.import_prospect(conn, mailbox, PAYLOAD)["receipt_id"]
    headers = {
        "X-OA-User": "cloud",
        "X-OA-Email": recipient,
        "X-Outreach-Approval-Key": "test-approval",
        "X-Outreach-Action": "confirm-v1",
    }
    assert app.get("/api/prospects", headers=headers).json()["items"] == []
    assert app.post(f"/api/prospects/{sid}/approval-token", headers=headers).status_code == 403
    o.assign(conn, mailbox, sid, owner, owner, "offer", recipient, 0)
    assert app.post(f"/api/prospects/{sid}/approval-token", headers=headers).status_code == 403
    o.assign(conn, mailbox, sid, recipient, owner, "accept", "", 1)
    token = app.post(f"/api/prospects/{sid}/approval-token", headers=headers).json()["token"]
    result = app.post(
        f"/api/prospects/{sid}/approve",
        headers=headers,
        json={"token": token, "steps": STEPS, "policy_confirmed": True, "sender": owner},
    )
    assert result.status_code == 200
    assert (
        conn.execute("SELECT address FROM prospect_sender WHERE sequence_id=?", (sid,)).fetchone()[
            0
        ]
        == recipient
    )
    assert transport.calls == []


def test_precontact_assignment_never_sends_and_rejects_previous_sender(conn, mailbox):
    o.init(conn)
    sid = o.import_prospect(conn, mailbox, PAYLOAD)["receipt_id"]
    owner, recipient = "larry@example.test", "cloud@example.test"
    offered = o.assign(conn, mailbox, sid, owner, owner, "offer", recipient, 0)
    assert offered == {"owner": owner, "pending": recipient, "version": 1}
    with pytest.raises(ValueError, match="完成或取消"):
        o.approve(conn, mailbox, sid, owner, STEPS, True, sender=owner)
    with pytest.raises(PermissionError):
        o.assign(conn, mailbox, sid, "other@example.test", owner, "accept", "", 1)
    accepted = o.assign(conn, mailbox, sid, recipient, owner, "accept", "", 1)
    assert accepted["owner"] == recipient and accepted["pending"] == ""
    assert o.listing(conn, mailbox)[0]["assignment"] == accepted
    with pytest.raises(ValueError, match="已变化"):
        o.assign(conn, mailbox, sid, owner, owner, "offer", recipient, 0)
    with pytest.raises(PermissionError, match="不是当前"):
        o.approve(conn, mailbox, sid, owner, STEPS, True, sender=owner)
    assert o.get(conn, mailbox, sid)["state"] == "draft"
    assert conn.execute("SELECT count(*) FROM prospect_step").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM message").fetchone()[0] == 0
    transport = Transport()
    assert not o.tick(
        conn, mailbox, sender=recipient, sender_name="Cloud", transport=transport, enabled=True
    )
    assert transport.calls == []
    o.approve(conn, mailbox, sid, recipient, STEPS, True, sender=recipient)
    with pytest.raises(ValueError, match="首次批准"):
        o.assign(conn, mailbox, sid, recipient, owner, "offer", owner, 2)
    assert not o.tick(
        conn, mailbox, sender=owner, sender_name="Larry", transport=transport, enabled=True
    )
    assert o.get(conn, mailbox, sid)["state"] == "active"
    assert transport.calls == []
    old, _ = store_raw(
        conn,
        mailbox,
        make_raw(
            from_=owner, to=PAYLOAD["email"], subject=STEPS[0]["subject"], message_id="<old@test>"
        ),
        "out",
        datetime.now(UTC),
    )
    old_thread = conn.execute("SELECT thread_id FROM message WHERE id=?", (old,)).fetchone()[0]
    assert o.tick(
        conn, mailbox, sender=recipient, sender_name="Cloud", transport=transport, enabled=True
    )
    assert transport.calls[0][0] == recipient
    inherited = conn.execute("SELECT * FROM followup").fetchone()
    assert inherited["owner"] == recipient and inherited["pending"] == ""
    assert inherited["thread_id"] != old_thread
    assert conn.execute("SELECT action FROM followup_event").fetchone()[0] == "prospect_assigned"
    followup.transfer(conn, inherited["thread_id"], recipient, owner, 1, {}, "handoff")
    assert o.get(conn, mailbox, sid)["state"] == "paused"
    followup.decide(conn, inherited["thread_id"], recipient, 2, "cancel")
    assert o.get(conn, mailbox, sid)["state"] == "paused"  # Cancel does not reauthorize sending.
    assert not o.tick(
        conn,
        mailbox,
        sender=recipient,
        sender_name="Cloud",
        transport=transport,
        enabled=True,
        now=datetime.now(UTC) + timedelta(days=8),
    )
    assert len(transport.calls) == 1
