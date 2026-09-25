import json

import pytest

from aimail import __main__ as service
from aimail.config import Config
from aimail.send.accounts import receiving_configs


def test_personal_imap_is_explicit_and_credentials_are_not_echoed(monkeypatch):
    for key, value in {
        "MAILBOX": "larry@example.test",
        "IMAP_HOST": "imap.test",
        "IMAP_USER": "larry@example.test",
        "IMAP_PASSWORD": "main-secret",
        "FOLLOWUP_MEMBERS": "cloud@example.test",
    }.items():
        monkeypatch.setenv(key, value)
    base = Config.from_env()
    entry = {"address": "cloud@example.test", "host": "smtp.test", "password_env": "CLOUD_SMTP"}
    env = {"SENDING_ACCOUNTS": json.dumps([entry]), "CLOUD_SMTP": "smtp-secret"}
    assert receiving_configs(base, env) == ()
    entry.update(imap_host="imap.test", imap_password_env="CLOUD_IMAP")
    env["SENDING_ACCOUNTS"] = json.dumps([entry])
    with pytest.raises(ValueError) as error:
        receiving_configs(base, env)
    assert "secret" not in str(error.value)
    env["CLOUD_IMAP"] = "imap-secret"
    (personal,) = receiving_configs(base, env)
    assert personal.imap_user == personal.smtp_user == "cloud@example.test"
    assert personal.imap_password == "imap-secret" and personal.smtp_password == "smtp-secret"
    assert base.imap_user == "larry@example.test"


def test_failed_personal_sync_never_calls_outreach(monkeypatch):
    def fail(*args):
        raise ConnectionError("test failure")

    calls = []
    monkeypatch.setattr(service, "_ingest_all", fail)
    monkeypatch.setattr(service.outreach, "tick", lambda *args, **kwargs: calls.append(True))
    with pytest.raises(ConnectionError):
        service._poll_personal_once(None, 2, 1)
    assert calls == []


def test_personal_manual_sync_is_bound_to_selected_authorized_mailbox(conn, monkeypatch):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from aimail.api.app import create_app
    from aimail.store import repo

    larry = SimpleNamespace(mailbox="larry@example.test")
    cloud = SimpleNamespace(mailbox="cloud@example.test")
    main_id = repo.ensure_mailbox(conn, larry.mailbox)
    cloud_id = repo.ensure_mailbox(conn, cloud.mailbox)
    calls = []
    monkeypatch.setattr(service, "_ingest_all", lambda c, mid: calls.append((c.mailbox, mid)))
    app = TestClient(
        create_app(
            conn,
            main_id,
            require_oa_auth=True,
            sync_mailboxes=service._sync_callbacks(((larry, main_id), (cloud, cloud_id))),
        )
    )
    headers = {"X-OA-User": "cloud", "X-OA-Email": cloud.mailbox}
    assert app.post("/api/sync", headers=headers).status_code == 200
    assert calls == [(cloud.mailbox, cloud_id)]
    assert (
        app.post(
            "/api/sync",
            headers={
                **headers,
                "X-Mailbox-Address": larry.mailbox,
            },
        ).status_code
        == 403
    )
    assert calls == [(cloud.mailbox, cloud_id)]
    assert (
        app.post(
            "/api/sync",
            headers={
                "X-OA-User": "larry",
                "X-OA-Email": larry.mailbox,
            },
        ).status_code
        == 200
    )
    assert calls[-1] == (larry.mailbox, main_id)
