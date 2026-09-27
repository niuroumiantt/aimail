import io
import zipfile
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from aimail import backends
from aimail.api.app import create_app
from aimail.api.followup import Summary
from aimail.ingest.run import store_raw
from aimail.store import repo
from conftest import make_raw


def test_leadsgen_grants_one_shared_mail_thread_without_mailbox_access(conn):
    shared = repo.ensure_mailbox(conn, "sales@glocalstorage.com")
    repo.ensure_mailbox(conn, "isaac@semifly.ai")
    pk, _ = store_raw(
        conn,
        shared,
        make_raw(attachments=[("spec.txt", b"spec evidence", "text/plain")]),
        "in",
        datetime.now(UTC),
    )
    thread_id = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    isaac = "isaac@semifly.ai"
    larry = "larry@glocalstorage.com"
    token = "trusted-leadsgen-test-token"
    app = TestClient(
        create_app(
            conn,
            shared,
            require_oa_auth=True,
            mailbox_access={
                larry: ("sales@glocalstorage.com", larry),
                isaac: ("isaac@semifly.ai",),
            },
            followup_members=(larry, isaac),
            outreach_import_token=token,
        )
    )
    headers = {"X-OA-User": isaac, "X-OA-Email": isaac}
    assert app.get("/api/mailboxes", headers=headers).json()["items"] == [
        {"address": "isaac@semifly.ai", "display_name": "", "tasks": ["draft", "leads", "read"]}
    ]
    grant_payload = {"external_id": "mail_123", "thread_id": thread_id, "recipient": isaac}
    first_grant = app.post(
        "/v1/followups/access",
        headers={"Authorization": "Bearer " + token},
        json=grant_payload,
    ).json()
    assert first_grant["owner"] == isaac
    assert (
        app.post(
            "/v1/followups/access",
            headers={"Authorization": "Bearer " + token},
            json=grant_payload,
        ).json()["version"]
        == first_grant["version"]
    )
    assert (
        app.post(
            "/v1/followups/access",
            headers={"Authorization": "Bearer wrong"},
            json={"external_id": "mail_456", "thread_id": thread_id, "recipient": isaac},
        ).status_code
        == 401
    )
    assert app.get("/api/threads", headers=headers).status_code == 200
    assert app.get(f"/api/threads/{thread_id}", headers=headers).status_code == 404
    assert (
        app.post(
            "/v1/followups/access",
            headers={"Authorization": "Bearer " + token},
            json={
                "external_id": "mail_456",
                "thread_id": thread_id,
                "recipient": "other@example.com",
            },
        ).status_code
        == 422
    )
    followups = app.get("/api/followups", headers=headers).json()["items"]
    assert [item["thread_id"] for item in followups] == [thread_id]
    detail = app.get(f"/api/followups/{thread_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["thread"]["messages"]
    exported = app.get(f"/api/followups/{thread_id}/history.zip", headers=headers)
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert archive.namelist() == [f"message-{pk}.eml"]
        assert b"spec.txt" in archive.read(f"message-{pk}.eml")
    moved = app.post(
        "/v1/followups/access",
        headers={"Authorization": "Bearer " + token},
        json={"external_id": "mail_123", "thread_id": thread_id, "recipient": larry},
    )
    assert moved.json()["owner"] == larry
    assert app.get(f"/api/followups/{thread_id}", headers=headers).status_code == 403
    assert (
        app.get(
            f"/api/followups/{thread_id}", headers={"X-OA-User": larry, "X-OA-Email": larry}
        ).status_code
        == 200
    )
    other_headers = {"X-OA-User": "other", "X-OA-Email": "other@example.com"}
    assert app.get("/api/followups", headers=other_headers).status_code == 403


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
    assert (
        app.post(
            f"/api/followups/{tid}/read", headers=headers(jane), json={"last_message_id": pk}
        ).status_code
        == 403
    )
    assert (
        app.post(
            f"/api/followups/{tid}/read", headers=headers(cloud), json={"last_message_id": second}
        ).status_code
        == 422
    )
    # A new arrival after the displayed snapshot must remain unread.
    newer, _ = store_raw(
        conn,
        box,
        make_raw(message_id="<new@x>", in_reply_to="<a@aurora.test>"),
        "in",
        datetime.now(UTC),
    )
    assert (
        app.post(
            f"/api/followups/{tid}/read", headers=headers(cloud), json={"last_message_id": pk}
        ).status_code
        == 200
    )
    assert unread(cloud) == 1
    assert unread(larry) == 2  # Read state is personal, not shared between salespeople.
    assert (
        app.post(
            f"/api/followups/{tid}/read", headers=headers(cloud), json={"last_message_id": newer}
        ).status_code
        == 200
    )
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


def test_internal_notification_idempotency_attachments_and_unknown_send(conn):
    from email import policy
    from email.parser import BytesParser

    from aimail.send.accounts import SendingAccount

    class Transport:
        def __init__(self):
            self.messages = []
            self.fail = False

        def deliver(self, sender, recipients, raw):
            self.messages.append((sender, recipients, raw))
            if self.fail:
                raise TimeoutError("provider uncertain")
            return "ok"

    transport = Transport()
    larry, isaac = "larry@glocalstorage.com", "isaac@semifly.ai"
    mid = repo.ensure_mailbox(conn, "sales@glocalstorage.com")
    pk, _ = store_raw(
        conn,
        mid,
        make_raw(attachments=[("spec.txt", b"evidence", "text/plain")]),
        "in",
        datetime.now(UTC),
    )
    tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    app = TestClient(
        create_app(
            conn,
            mid,
            require_oa_auth=True,
            mailbox_access={larry: ("sales@glocalstorage.com",)},
            followup_members=(larry, isaac),
            sending_accounts={larry: SendingAccount(larry, "Larry", transport)},
            outreach_import_token="test",
        )
    )
    payload = dict(
        account_id="lead1",
        version=1,
        actor=larry,
        recipient=isaac,
        subject="20 servers",
        summary="<unsafe>需求摘要",
        thread_id=tid,
    )
    assert app.post("/v1/handoff-notifications", json=payload).status_code == 401
    headers = {"Authorization": "Bearer test"}
    assert (
        app.post(
            "/v1/handoff-notifications",
            json={**payload, "recipient": "customer@example.com"},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        app.post("/v1/handoff-notifications", json=payload, headers=headers).json()["state"]
        == "sent"
    )
    assert (
        app.post("/v1/handoff-notifications", json=payload, headers=headers).json()["state"]
        == "sent"
    )
    assert len(transport.messages) == 1
    message = BytesParser(policy=policy.default).parsebytes(transport.messages[0][2])
    assert message["To"] == isaac
    assert "&lt;unsafe&gt;" in message.get_body(preferencelist=("html",)).get_content()
    attachment = next(message.iter_attachments())
    assert attachment.get_content_type() == "message/rfc822"
    assert (
        next(attachment.get_payload()[0].iter_attachments()).get_payload(decode=True) == b"evidence"
    )
    transport.fail = True
    payload["version"] = 2
    assert (
        app.post("/v1/handoff-notifications", json=payload, headers=headers).json()["state"]
        == "unknown"
    )
    assert (
        app.post("/v1/handoff-notifications", json=payload, headers=headers).json()["state"]
        == "unknown"
    )
    assert len(transport.messages) == 2


def test_projection_export_and_employee_decision_are_scoped_to_shared_threads(conn):
    from aimail.store import followup

    shared = repo.ensure_mailbox(conn, "sales@glocalstorage.com")
    private = repo.ensure_mailbox(conn, "larry@glocalstorage.com")
    tids = []
    for mailbox in [shared, private]:
        pk, _ = store_raw(conn, mailbox, make_raw(subject=str(mailbox)), "in", datetime.now(UTC))
        tids.append(conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0])
    client = TestClient(
        create_app(
            conn,
            shared,
            require_oa_auth=True,
            followup_members=("larry@example.com", "isaac@example.com"),
            outreach_import_token="test",
        )
    )
    for tid in tids:
        followup.transfer(
            conn, tid, "larry@example.com", "isaac@example.com", 0, {"needs": "summary"}, "note"
        )
    headers = {"Authorization": "Bearer test"}
    assert client.get("/v1/followups").status_code == 401
    rows = client.get("/v1/followups", headers=headers).json()["items"]
    assert [r["thread_id"] for r in rows] == [tids[0]]
    assert "payload" not in rows[0]["history"][0]
    payload = dict(actor="isaac@example.com", version=1, action="decline", reason="不熟悉产品")
    assert (
        client.post(f"/v1/followups/{tids[1]}/decision", headers=headers, json=payload).status_code
        == 403
    )
    assert (
        client.post(f"/v1/followups/{tids[0]}/decision", headers=headers, json=payload).status_code
        == 200
    )
    assert (
        client.post(f"/v1/followups/{tids[0]}/decision", headers=headers, json=payload).status_code
        == 409
    )
    result = client.get("/v1/followups", headers=headers).json()["items"][0]
    assert result["pending"] == ""
    assert result["history"][-1]["reason"] == "不熟悉产品"


def test_explicit_pipeline_mailboxes_include_sales_and_primary_handoffs_only(conn):
    from aimail.store import followup

    primary = repo.ensure_mailbox(conn, "larry@example.com")
    shared = repo.ensure_mailbox(conn, "sales@example.com")
    private = repo.ensure_mailbox(conn, "isaac@example.com")
    tids = []
    for mid in (primary, shared, private):
        pk, _ = store_raw(conn, mid, make_raw(subject=f"Source {mid}"), "in", datetime.now(UTC))
        tids.append(conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0])
    client = TestClient(
        create_app(
            conn,
            primary,
            shared_mailbox_id=shared,
            require_oa_auth=True,
            outreach_import_token="test",
            followup_members=("larry@example.com", "isaac@example.com"),
        )
    )
    for tid in tids:
        followup.transfer(conn, tid, "larry@example.com", "isaac@example.com", 0, {}, "")
    headers = {"Authorization": "Bearer test"}
    items = client.get("/v1/followups", headers=headers).json()["items"]
    assert [i["thread_id"] for i in items] == tids[:2]
    for tid in tids:
        r = client.post(
            f"/v1/followups/{tid}/decision",
            headers=headers,
            json=dict(actor="isaac@example.com", version=1, action="accept"),
        )
        assert r.status_code == (403 if tid == tids[2] else 200)
