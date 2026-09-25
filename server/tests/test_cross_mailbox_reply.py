"""Only accepted handoffs and recorded personal sends permit cross-mailbox joining."""

from datetime import UTC, datetime

import pytest

from conftest import make_raw
from mail2leads.ingest.run import store_raw
from mail2leads.store import followup, repo

NOW = datetime(2026, 9, 25, tzinfo=UTC)


@pytest.mark.parametrize("variation,joins", [
    ("accepted", True),
    ("pending", False),
    ("other_customer", False),
    ("unrecorded", False),
    ("subject_only", False),
    ("references_only", True),
    ("reassigned", False),
])
def test_personal_reply_requires_assignment_and_recorded_send(conn, mailbox, variation, joins):
    followup.init(conn)
    personal = repo.ensure_mailbox(conn, "cloud@example.test")
    pk, _ = store_raw(conn, mailbox, make_raw(message_id="<initial@test>"), "in", NOW)
    tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    followup.transfer(conn, tid, "sales@example.test", "cloud@example.test", 0, {}, "")
    if variation != "pending":
        followup.decide(conn, tid, "cloud@example.test", 1, "accept")
    sent, _ = store_raw(conn, mailbox, make_raw(
        message_id="<personal@test>", from_="cloud@example.test", to="mikko@aurora.test",
        in_reply_to="<initial@test>",
    ), "out", NOW)
    if variation != "unrecorded":
        conn.execute(
            "INSERT INTO outbound(mailbox_id,thread_id,message_pk,sent_by,sent_at) "
            "VALUES(?,?,?,?,?)", (mailbox, tid, sent, "cloud@example.test", NOW.isoformat()),
        )
    if variation == "reassigned":
        followup.transfer(conn, tid, "cloud@example.test", "next@example.test", 2, {}, "")
        followup.decide(conn, tid, "next@example.test", 3, "accept")
    reply, _ = store_raw(conn, personal, make_raw(
        message_id="<reply@test>", to="cloud@example.test",
        from_="stranger@other.test" if variation == "other_customer" else "mikko@aurora.test",
        in_reply_to="" if variation in {"subject_only", "references_only"} else "<personal@test>",
        references="<personal@test>" if variation == "references_only" else "",
    ), "in", NOW)
    row = conn.execute("SELECT thread_id,mailbox_id FROM message WHERE id=?", (reply,)).fetchone()
    assert (row["thread_id"] == tid) is joins
    assert row["mailbox_id"] == personal  # Preserve where the original was actually received.
