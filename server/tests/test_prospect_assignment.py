import pytest

from mail2leads import outreach as o
from test_outreach import PAYLOAD, STEPS, Transport


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
