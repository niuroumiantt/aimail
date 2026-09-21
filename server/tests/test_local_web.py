from datetime import UTC, datetime

from fastapi.testclient import TestClient

from conftest import make_raw
from mail2leads.ingest.run import store_raw
from mail2leads.local_web import create_local_app
from mail2leads.store import repo
from mail2leads.store.db import connect


def test_real_mail_read_only_and_origin_guard(tmp_path):
    conn = connect(tmp_path / "mailbox.sqlite3")
    mailbox = repo.ensure_mailbox(conn, "sales@example.test")
    store_raw(
        conn,
        mailbox,
        make_raw(
            body="Actual original", attachments=[("spec.txt", b"attachment body", "text/plain")]
        ),
        "in",
        datetime.now(UTC),
    )
    conn.close()
    with TestClient(create_local_app(tmp_path)) as client:
        response = client.get("/mail/threads")
        assert response.headers["cache-control"] == "no-store"
        data = response.json()
        assert data["messages"] == 1
        assert data["threads"][0]["reading"] is None
        detail = client.get(f"/mail/threads/{data['threads'][0]['id']}").json()
        assert detail["messages"][0]["body_new"].strip() == "Actual original"
        assert detail["messages"][0]["attachments"][0]["filename"] == "spec.txt"
        assert "attachment body" not in str(detail)
        assert (
            client.get("/mail/threads", headers={"Origin": "https://evil.test"}).status_code == 403
        )
        assert client.get("/mail/threads", headers={"Host": "evil.test"}).status_code == 403
        assert client.post("/mail/send").status_code == 404
        assert client.delete("/mail/threads/1").status_code == 405


def test_missing_database_is_not_demo_fallback(tmp_path):
    with TestClient(create_local_app(tmp_path)) as client:
        assert client.get("/mail/threads").status_code == 503
