import sqlite3
import threading
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from conftest import make_raw
from mail2leads import backends
from mail2leads.ingest.run import store_raw
from mail2leads.local_web import create_local_app
from mail2leads.store import repo
from mail2leads.store.db import connect
from mail2leads.tasks.ask_mailbox import Answer, validate_answer


def test_citations_and_numbers():
    sources = [{"id": 1, "thread_id": 2, "subject": "RFQ", "sent_at": "", "text": "32 servers"}]
    valid = Answer(findings=[{"text": "32 台", "source_id": 1, "quote": "32 servers"}])
    assert not validate_answer(valid, sources)[0]["unverified"]
    valid.findings[0].text = "999 台"
    assert validate_answer(valid, sources)[0]["unverified"] == ["999"]
    valid.findings[0].quote = "made up"
    with pytest.raises(backends.LLMError):
        validate_answer(valid, sources)
    valid.findings[0].source_id = 99
    with pytest.raises(backends.LLMError):
        validate_answer(valid, sources)


def test_ask_cross_topic_and_clear_preserves_audit(tmp_path, monkeypatch):
    conn = connect(tmp_path / "mailbox.sqlite3")
    mailbox = repo.ensure_mailbox(conn, "sales@example.test")
    for i in range(2):
        store_raw(
            conn,
            mailbox,
            make_raw(subject=f"RFQ {i}", message_id=f"<{i}@test>", body=f"{i} servers"),
            "in",
            datetime.now(UTC),
        )
    conn.close()

    def answer(question, sources, history):
        assert len(sources) == 2
        assert question == "哪些询价？"
        assert not history
        return []

    monkeypatch.setattr("mail2leads.tasks.ask_mailbox.ask", answer)
    with TestClient(create_local_app(tmp_path)) as client:
        assert client.post("/mail/assistant", json={"question": " "}).status_code == 422
        assert client.post("/mail/assistant", json={"question": "哪些询价？"}).status_code == 200
        for _ in range(100):
            if client.get("/mail/job").json()["status"] != "running":
                break
            time.sleep(0.01)
        turns = client.get("/mail/assistant").json()["turns"]
        assert turns[0]["status"] == "done"
        assert turns[0]["scope"]["total"] == 2
        assert client.post("/mail/assistant/clear").status_code == 200
        assert not client.get("/mail/assistant").json()["turns"]
    conn = connect(tmp_path / "mailbox.sqlite3")
    assert conn.execute("SELECT COUNT(*) FROM assistant_event").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM message").fetchone()[0] == 2
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM assistant_event")
    conn.close()


def test_busy_refuses_duplicate_and_clear(tmp_path, monkeypatch):
    conn = connect(tmp_path / "mailbox.sqlite3")
    mailbox = repo.ensure_mailbox(conn, "sales@example.test")
    store_raw(conn, mailbox, make_raw(), "in", datetime.now(UTC))
    conn.close()
    release = threading.Event()
    monkeypatch.setattr("mail2leads.tasks.ask_mailbox.ask", lambda *args: release.wait(3) and [])
    with TestClient(create_local_app(tmp_path)) as client:
        try:
            assert client.post("/mail/assistant", json={"question": "test"}).status_code == 200
            assert client.post("/mail/assistant", json={"question": "test"}).status_code == 409
            assert client.post("/mail/assistant/clear").status_code == 409
        finally:
            release.set()
        for _ in range(100):
            if client.get("/mail/job").json()["status"] != "running":
                break
            time.sleep(0.01)
