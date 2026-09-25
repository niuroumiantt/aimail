import pytest
from fastapi.testclient import TestClient

from mail2leads import outreach as o
from mail2leads.api.app import create_app
from mail2leads.send.accounts import SendingAccount
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
    assert o.tick(
        conn, mailbox, sender=recipient, sender_name="Cloud", transport=transport, enabled=True
    )
    assert transport.calls[0][0] == recipient
