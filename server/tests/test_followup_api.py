import io
import zipfile
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from conftest import make_raw
from mail2leads import backends
from mail2leads.api.app import create_app
from mail2leads.api.followup import Summary
from mail2leads.ingest.run import store_raw
from mail2leads.store import repo


def test_thread_scoped_transfer_exports_attachments_without_granting_mailbox(conn, monkeypatch):
    box = repo.ensure_mailbox(conn, "sales@glocalstorage.com")
    raw = make_raw(attachments=[("spec.txt", b"spec evidence", "text/plain")])
    pk, _ = store_raw(conn, box, raw, "in", datetime.now(UTC))
    tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    second, _ = store_raw(
        conn, box, make_raw(message_id="<private@x>", subject="private"), "in", datetime.now(UTC)
    )
    private_tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (second,)).fetchone()[0]
    larry, cloud, jane = (f"{x}@glocalstorage.com" for x in ("larry", "cloud", "jane"))
    app = TestClient(
        create_app(
            conn,
            box,
            require_oa_auth=True,
            mailbox_access={larry: ("sales@glocalstorage.com",)},
            followup_members=(larry, cloud, jane),
        )
    )

    def headers(address):
        return {"X-OA-User": address, "X-OA-Email": address}

    monkeypatch.setattr(backends, "ready", lambda: (True, ""))
    monkeypatch.setattr(backends, "describe", lambda: "test model")
    monkeypatch.setattr(
        backends,
        "complete",
        lambda *args: Summary(
            stage="询盘",
            needs="未提及",
            commitments="未提及",
            open_questions="规格",
            next_steps="确认规格",
            source_ids=[pk],
        ),
    )
    assert (
        app.post(
            f"/api/followups/{tid}/offer",
            headers=headers(larry),
            json={"recipient": cloud, "version": 0},
        ).status_code
        == 200
    )
    assert app.get(f"/api/followups/{tid}", headers=headers(cloud)).status_code == 200
    detail = app.get(f"/api/followups/{tid}", headers=headers(cloud)).json()
    assert detail["thread"]["history"] == []
    assert app.get(f"/api/followups/{tid}", headers=headers(jane)).status_code == 403
    assert app.get(f"/api/followups/{private_tid}", headers=headers(cloud)).status_code == 403
    assert app.get("/api/threads", headers=headers(cloud)).status_code == 403
    def unread(who):
        return app.get("/api/followups", headers=headers(who)).json()["items"][0]["unread_count"]

    assert unread(cloud) == 1
    assert app.post(f"/api/followups/{tid}/read", headers=headers(jane),
                    json={"last_message_id": pk}).status_code == 403
    assert app.post(f"/api/followups/{tid}/read", headers=headers(cloud),
                    json={"last_message_id": second}).status_code == 422
    # A new arrival after the displayed snapshot must remain unread.
    newer, _ = store_raw(conn, box, make_raw(message_id="<new@x>", in_reply_to="<a@aurora.test>"),
                         "in", datetime.now(UTC))
    assert app.post(f"/api/followups/{tid}/read", headers=headers(cloud),
                    json={"last_message_id": pk}).status_code == 200
    assert unread(cloud) == 1
    assert unread(larry) == 2  # Read state is personal, not shared between salespeople.
    assert app.post(f"/api/followups/{tid}/read", headers=headers(cloud),
                    json={"last_message_id": newer}).status_code == 200
    assert unread(cloud) == 0
    result = app.get(f"/api/followups/{tid}/history.zip", headers=headers(cloud))
    assert result.status_code == 200
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert archive.read(f"message-{pk}.eml") == raw
        assert len(archive.namelist()) == 2
    assert (
        app.post(
            f"/api/followups/{tid}/accept", headers=headers(cloud), json={"version": 1}
        ).status_code
        == 200
    )
    assert (
        app.post(
            f"/api/followups/{tid}/offer",
            headers=headers(cloud),
            json={"recipient": jane, "version": 2},
        ).status_code
        == 200
    )
    conn.execute(
        "INSERT INTO reply_attempt(thread_id,token_hash,sender,actor,raw,state,created_at) "
        "VALUES(?,?,?,?,?,'unknown',?)",
        (tid, "test-token-hash", cloud, cloud, raw, datetime.now(UTC).isoformat()),
    )
    pending = app.get(f"/api/followups/{tid}", headers=headers(cloud)).json()["unresolved_send"]
    assert pending["sender"] == cloud and pending["state"] == "unknown"
    assert "raw" not in pending and "token_hash" not in pending
    assert app.post(f"/api/followups/{tid}/reply-token", headers=headers(cloud)).status_code == 409
    result = app.get(f"/api/followups/{tid}/unresolved.eml", headers=headers(cloud))
    assert result.content == raw and result.headers["cache-control"] == "no-store"
    # Pending recipient and former owner cannot download another person's unresolved send.
    assert app.get(f"/api/followups/{tid}/unresolved.eml", headers=headers(jane)).status_code == 403
    previous = app.get(f"/api/followups/{tid}/unresolved.eml", headers=headers(larry))
    assert previous.status_code == 403


def test_model_failure_leaves_no_transfer(conn, monkeypatch):
    box = repo.ensure_mailbox(conn, "sales@glocalstorage.com")
    pk, _ = store_raw(conn, box, make_raw(), "in", datetime.now(UTC))
    tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    larry, cloud = "larry@glocalstorage.com", "cloud@glocalstorage.com"
    app = TestClient(
        create_app(
            conn,
            box,
            require_oa_auth=True,
            mailbox_access={larry: ("sales@glocalstorage.com",)},
            followup_members=(larry, cloud),
        )
    )
    monkeypatch.setattr(backends, "ready", lambda: (False, "missing"))
    result = app.post(
        f"/api/followups/{tid}/offer",
        headers={"X-OA-User": "admin", "X-OA-Email": larry},
        json={"recipient": cloud, "version": 0},
    )
    assert result.status_code == 503
    assert conn.execute("SELECT count(*) FROM followup").fetchone()[0] == 0
