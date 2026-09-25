"""Receive access never grants another employee's sending identity."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from aimail.api.app import create_app
from aimail.config import Config
from aimail.ingest.run import store_raw
from aimail.send import SmtpTransport, build_message
from aimail.store import repo
from conftest import make_raw


def test_receive_credentials_do_not_enable_sending(monkeypatch):
    for key in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    for key, value in {
        "MAILBOX": "sales@glocalstorage.com",
        "IMAP_HOST": "imap.example.test",
        "IMAP_USER": "sales@glocalstorage.com",
        "IMAP_PASSWORD": "receive-only",
    }.items():
        monkeypatch.setenv(key, value)
    config = Config.from_env()
    assert (config.smtp_host, config.smtp_user, config.smtp_password) == ("", "", "")


def test_sales_is_blocked_before_smtp_or_message_creation():
    with pytest.raises(PermissionError, match="只收信"):
        SmtpTransport("unused", 465, "sales@glocalstorage.com", "unused").deliver(
            "Sales@GlocalStorage.com", ["customer@example.test"], b"unused"
        )
    with pytest.raises(PermissionError, match="只收信"):
        build_message(
            sender="sales@glocalstorage.com",
            sender_name="",
            to=["a@b.test"],
            subject="test",
            body="test",
            in_reply_to="",
            references="",
            now=datetime.now(UTC),
        )


def test_smtp_requires_explicit_matching_personal_identity():
    with pytest.raises(PermissionError, match="明确配置"):
        SmtpTransport("", 465, "", "").deliver("larry@glocalstorage.com", [], b"")
    with pytest.raises(PermissionError, match="不一致"):
        SmtpTransport("unused", 465, "larry@glocalstorage.com", "unused").deliver(
            "cloud@glocalstorage.com", [], b""
        )


def test_reader_cannot_borrow_global_sender(conn):
    mailbox = repo.ensure_mailbox(conn, "sales@glocalstorage.com")
    pk, _ = store_raw(conn, mailbox, make_raw(), "in", datetime.now(UTC))
    tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    app = TestClient(
        create_app(
            conn,
            mailbox,
            sender="larry@glocalstorage.com",
            require_oa_auth=True,
            mailbox_access={
                "cloud@glocalstorage.com": ("sales@glocalstorage.com",),
                "larry@glocalstorage.com": ("sales@glocalstorage.com",),
            },
        )
    )
    headers = {"X-OA-User": "cloud", "X-OA-Email": "cloud@glocalstorage.com"}
    assert app.get(f"/api/threads/{tid}", headers=headers).status_code == 200
    assert app.post(f"/api/threads/{tid}/send-token", headers=headers).status_code == 403
    headers = {"X-OA-User": "admin", "X-OA-Email": "larry@glocalstorage.com"}
    assert app.post(f"/api/threads/{tid}/send-token", headers=headers).status_code == 200
