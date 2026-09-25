import json

import pytest

from mail2leads import __main__ as service
from mail2leads.config import Config
from mail2leads.send.accounts import receiving_configs


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
