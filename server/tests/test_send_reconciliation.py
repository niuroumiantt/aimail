import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from aimail.api.app import create_app
from aimail.ingest.parse import parse
from aimail.ingest.run import store_raw
from aimail.send import TokenBox, build_message, send
from aimail.send.reconcile import resolve
from aimail.store import followup, repo
from conftest import make_raw


def pending_attempt(conn, *, state="unknown", created_at=None):
    mailbox_id = repo.ensure_mailbox(conn, "larry@glocalstorage.com")
    incoming = make_raw()
    pk, _ = store_raw(conn, mailbox_id, incoming, "in", datetime.now(UTC))
    thread_id = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    received = parse(incoming)
    now = datetime.now(UTC)
    message, _ = build_message(
        sender="larry@glocalstorage.com",
        sender_name="Larry",
        to=[received.from_email],
        subject=f"Re: {received.subject}",
        body="A prepared reply",
        in_reply_to=received.message_id,
        references="",
        now=now,
    )
    raw = message.as_bytes()
    attempt_id = conn.execute(
        "INSERT INTO reply_attempt(thread_id,token_hash,sender,actor,raw,state,created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (
            thread_id,
            f"token-{state}-{created_at}",
            "larry@glocalstorage.com",
            "larry@glocalstorage.com",
            raw,
            state,
            (created_at or now).isoformat(),
        ),
    ).lastrowid
    return mailbox_id, thread_id, attempt_id, raw


def test_confirmed_sent_is_recorded_without_calling_mail_transport(conn):
    mailbox_id, thread_id, attempt_id, raw = pending_attempt(conn)
    with pytest.raises(PermissionError, match="当前负责人"):
        resolve(
            conn,
            thread_id=thread_id,
            attempt_id=attempt_id,
            actor="cloud@glocalstorage.com",
            outcome="sent",
            evidence_reference="163 delivery log 783412",
        )
    result = resolve(
        conn,
        thread_id=thread_id,
        attempt_id=attempt_id,
        actor="larry@glocalstorage.com",
        outcome="sent",
        evidence_reference="163 delivery log 783412",
    )
    assert result == {"ok": True, "already_resolved": False, "outcome": "sent"}
    attempt = conn.execute("SELECT state FROM reply_attempt WHERE id=?", (attempt_id,)).fetchone()
    assert attempt["state"] == "recorded"
    resolution = conn.execute(
        "SELECT * FROM reply_resolution WHERE attempt_id=?", (attempt_id,)
    ).fetchone()
    message = conn.execute(
        "SELECT * FROM message WHERE id=?", (resolution["message_pk"],)
    ).fetchone()
    assert message["thread_id"] == thread_id and message["mailbox_id"] == mailbox_id
    assert message["direction"] == "out" and bytes(message["raw"]) == raw
    outbound = conn.execute(
        "SELECT * FROM outbound WHERE message_pk=?", (message["id"],)
    ).fetchone()
    assert outbound["sent_by"] == "larry@glocalstorage.com"
    assert outbound["transport_result"] == "manually_confirmed_by_provider_evidence"
    assert (
        conn.execute("SELECT folder FROM thread WHERE id=?", (thread_id,)).fetchone()[0]
        == "replied"
    )
    with pytest.raises(sqlite3.IntegrityError, match="追加审计"):
        conn.execute(
            "UPDATE reply_resolution SET evidence_reference='overwritten' WHERE attempt_id=?",
            (attempt_id,),
        )
    # An identical retry after an HTTP timeout is idempotent and cannot duplicate the message.
    assert resolve(
        conn,
        thread_id=thread_id,
        attempt_id=attempt_id,
        actor="larry@glocalstorage.com",
        outcome="sent",
        evidence_reference="163 delivery log 783412",
    )["already_resolved"]
    assert conn.execute("SELECT count(*) FROM outbound").fetchone()[0] == 1


def test_confirmed_not_sent_unlocks_only_after_provider_evidence(conn):
    _, thread_id, attempt_id, _ = pending_attempt(conn)
    result = resolve(
        conn,
        thread_id=thread_id,
        attempt_id=attempt_id,
        actor="larry@glocalstorage.com",
        outcome="not_sent",
        evidence_reference="163 rejection log 783413",
    )
    assert result["outcome"] == "not_sent"
    assert (
        conn.execute("SELECT state FROM reply_attempt WHERE id=?", (attempt_id,)).fetchone()[0]
        == "resolved_not_sent"
    )
    assert conn.execute("SELECT count(*) FROM outbound").fetchone()[0] == 0
    # A fresh explicit send attempt can now be created; reconciliation itself did not send.
    calls = []

    class TestTransport:
        def deliver(self, sender, recipients, raw):
            calls.append(raw)
            return "ok"

    send(
        conn,
        token=TokenBox().mint(thread_id, "larry@glocalstorage.com"),
        mailbox_id=1,
        sender="larry@glocalstorage.com",
        sender_name="Larry",
        thread_id=thread_id,
        to=["customer@example.test"],
        subject="Re: RFQ",
        body="Manually approved retry",
        transport=TestTransport(),
    )
    assert len(calls) == 1


def test_owner_only_confirmation_and_stale_sending_timeout(conn):
    mailbox_id, thread_id, attempt_id, _ = pending_attempt(
        conn, state="sending", created_at=datetime.now(UTC)
    )
    followup.init(conn)
    conn.execute(
        "INSERT INTO followup VALUES(?,?,?,?,?,?,?)",
        (thread_id, "larry@glocalstorage.com", "jane@glocalstorage.com", 1, "{}", "", "now"),
    )
    app = TestClient(
        create_app(
            conn,
            mailbox_id,
            require_oa_auth=True,
            mailbox_access={"larry@glocalstorage.com": ("larry@glocalstorage.com",)},
            followup_members=("larry@glocalstorage.com", "jane@glocalstorage.com"),
        )
    )

    def headers(user):
        return {"X-OA-User": user, "X-OA-Email": user}

    path = f"/api/followups/{thread_id}/unresolved/{attempt_id}/resolve"
    payload = {"outcome": "not_sent", "evidence_reference": "smtp log rejected 991"}
    assert (
        app.post(path, headers=headers("jane@glocalstorage.com"), json=payload).status_code == 403
    )
    assert (
        app.post(path, headers=headers("larry@glocalstorage.com"), json=payload).status_code == 409
    )
    conn.execute(
        "UPDATE reply_attempt SET created_at=? WHERE id=?",
        ((datetime.now(UTC) - timedelta(minutes=11)).isoformat(), attempt_id),
    )
    assert (
        app.post(path, headers=headers("larry@glocalstorage.com"), json=payload).status_code == 200
    )
    detail = app.get(
        f"/api/followups/{thread_id}", headers=headers("larry@glocalstorage.com")
    ).json()
    assert detail["unresolved_send"] is None
