import io
import json
import sqlite3
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from aimail.api.app import create_app
from aimail.api.local_mail import create_device
from aimail.ingest.run import store_raw
from aimail.store import repo
from conftest import make_raw
from sync_local_mail import sync


def test_scoped_complete_original_attachment_translation_retry_and_revocation(
    conn, mailbox, tmp_path, monkeypatch
):
    from email import policy
    from email.parser import BytesParser

    mail = BytesParser(policy=policy.default).parsebytes(make_raw(body="Need 12 units."))
    mail.add_attachment(
        b"%PDF-synthetic", maintype="application", subtype="pdf", filename="../../quote.pdf"
    )
    raw = mail.as_bytes()
    pk = store_raw(conn, mailbox, raw, "in", datetime.now(UTC))[0]
    private = repo.ensure_mailbox(conn, "private@example.test")
    other = store_raw(
        conn, private, make_raw(message_id="<private@test>"), "in", datetime.now(UTC)
    )[0]
    access = {"owner@example.test": ("sales@example.test",)}
    app = create_app(conn, mailbox, require_oa_auth=True, mailbox_access=access)
    device = create_device(conn, "owner@example.test", "M5", access["owner@example.test"])
    conn.execute(
        "INSERT INTO message_translation(source_id,model,task_version,produced_at,status,payload) "
        "VALUES(?,'Fixture','translate_mail@2','2026-10-09','ok',?)",
        (pk, json.dumps({"text_zh": "需要 12 件。"})),
    )
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer " + device["token"]}
        assert client.get("/v1/local-mail/messages").status_code == 401
        assert (
            client.get(f"/v1/local-mail/messages/{other}/original", headers=headers).status_code
            == 404
        )
        assert [
            r["id"] for r in client.get("/v1/local-mail/messages", headers=headers).json()["items"]
        ] == [pk]

        class Opener:
            def open(self, request, **kwargs):
                response = client.get(
                    request.full_url.removeprefix("http://local.test"),
                    headers=dict(request.header_items()),
                )
                response.raise_for_status()
                return io.BytesIO(response.content)

        monkeypatch.setattr("urllib.request.build_opener", lambda *_args: Opener())
        root = tmp_path / "personal"
        config = {"endpoint": "http://local.test", "token": device["token"]}
        first = sync(config, root)
        second = sync(config, root)
        assert first["message"] == second["message"] == 1
        assert first["attachment"] == first["translation"] == 1
        with sqlite3.connect(root / "mail.sqlite3") as local:
            filename = local.execute("SELECT file FROM message").fetchone()[0]
            assert (root / filename).read_bytes() == raw
            attachment = local.execute("SELECT file FROM attachment").fetchone()[0]
            assert (root / attachment).read_bytes() == b"%PDF-synthetic"
            assert ".." not in attachment
        assert (root / "mail.sqlite3").stat().st_mode & 0o777 == 0o600
        access["owner@example.test"] = ()
        assert client.get("/v1/local-mail/messages", headers=headers).status_code == 403
        access["owner@example.test"] = ("sales@example.test",)
        conn.execute("UPDATE local_mail_device SET revoked_at='2026-10-09'")
        assert client.get("/v1/local-mail/messages", headers=headers).status_code == 401
        assert conn.execute("SELECT raw FROM message WHERE id=?", (pk,)).fetchone()[0] == raw
