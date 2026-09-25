import pytest

from conftest import make_raw
from mail2leads.ingest.run import store_raw
from mail2leads.store import followup


def seed(conn, mailbox):
    from datetime import UTC, datetime

    pk, _ = store_raw(conn, mailbox, make_raw(), "in", datetime.now(UTC))
    followup.init(conn)
    return conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]


def test_transfer_keeps_owner_until_acceptance_and_can_transfer_again(conn, mailbox):
    tid = seed(conn, mailbox)
    first = followup.transfer(conn, tid, "larry", "cloud", 0, {"stage": "inquiry"}, "follow up")
    assert first["owner"] == "larry" and first["pending"] == "cloud"
    accepted = followup.decide(conn, tid, "cloud", 1, "accept")
    assert accepted["owner"] == "cloud" and not accepted["pending"]
    followup.transfer(conn, tid, "cloud", "jane", 2, {"stage": "discussion"}, "")
    assert conn.execute("SELECT count(*) FROM followup_event").fetchone()[0] == 3


def test_stale_or_unauthorized_acceptance_does_not_change_responsibility(conn, mailbox):
    tid = seed(conn, mailbox)
    followup.transfer(conn, tid, "larry", "cloud", 0, {}, "")
    for actor, version in [("outsider", 1), ("cloud", 0)]:
        with pytest.raises(PermissionError):
            followup.decide(conn, tid, actor, version, "accept")
    with pytest.raises(ValueError):
        followup.transfer(conn, tid, "larry", "jane", 1, {}, "")
    followup.decide(conn, tid, "cloud", 1, "accept")
    with pytest.raises(PermissionError):
        followup.transfer(conn, tid, "larry", "jane", 2, {}, "")
    assert followup.get(conn, tid)["owner"] == "cloud"


def test_cancel_retains_owner_and_history(conn, mailbox):
    tid = seed(conn, mailbox)
    followup.transfer(conn, tid, "larry", "cloud", 0, {"source_ids": [1]}, "note")
    with pytest.raises(PermissionError):
        followup.decide(conn, tid, "cloud", 1, "cancel")
    state = followup.decide(conn, tid, "larry", 1, "cancel")
    assert state["owner"] == "larry" and state["pending"] == ""
    assert conn.execute("SELECT count(*) FROM followup_event").fetchone()[0] == 2
