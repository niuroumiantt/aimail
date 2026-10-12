"""Bulk deletion is a scoped, atomic and recoverable operation."""

from fastapi.testclient import TestClient

from aimail.api.app import create_app
from aimail.store import mail_state, repo
from test_mail_trash import PERSON, incoming, snapshot


def setup(conn, mailbox):
    a, _, _ = incoming(conn, mailbox, "<a@test>", subject="A")
    b, _, _ = incoming(conn, mailbox, "<b@test>", subject="B")
    client = TestClient(create_app(conn, mailbox))
    items = client.get("/api/threads").json()
    body = {
        "email": items[0]["email"],
        "threads": [{k: t[k] for k in ("id", "updated_at", "message_count")} for t in items],
    }
    return client, body, a, b


def test_group_trash_requires_warning_snapshot_and_preserves_originals(conn, mailbox):
    client, body, a, b = setup(conn, mailbox)
    before = snapshot(conn, ("thread", "message", "attachment", "ingest_cursor", "lead", "outbox"))
    assert client.post("/api/contact-group/trash", json=body).status_code == 401
    assert client.post("/api/contact-group/trash", json=body, headers=PERSON).status_code == 200
    assert client.get("/api/threads").json() == []
    assert len(client.get("/api/threads?folder=trash").json()) == 2
    assert snapshot(conn, tuple(before)) == before
    assert client.post("/api/contact-group/trash", json=body, headers=PERSON).status_code == 200
    assert conn.execute("SELECT count(*) FROM thread_mail_event").fetchone()[0] == 2
    assert client.post(f"/api/threads/{a}/restore", headers=PERSON).status_code == 200
    assert not mail_state.deleted_at(conn, a) and mail_state.deleted_at(conn, b)


def test_entire_batch_rejects_wrong_contact_mailbox_or_stale_message_count(conn, mailbox):
    client, body, a, b = setup(conn, mailbox)
    good = body["threads"][0].copy()
    body["threads"][0]["message_count"] += 1
    assert client.post("/api/contact-group/trash", json=body, headers=PERSON).status_code == 409
    body["threads"][0] = good
    body["email"] = "wrong@example.test"
    assert client.post("/api/contact-group/trash", json=body, headers=PERSON).status_code == 404
    other = repo.ensure_mailbox(conn, "private@example.test")
    c, _, _ = incoming(conn, other, "<private@test>")
    body["email"] = "mikko@aurora.test"
    body["threads"][1]["id"] = str(c)
    assert client.post("/api/contact-group/trash", json=body, headers=PERSON).status_code == 404
    assert not any(mail_state.deleted_at(conn, t) for t in (a, b, c))
