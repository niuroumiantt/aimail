from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from conftest import make_raw
from mail2leads import fact_store
from mail2leads.ingest.run import store_raw
from mail2leads.local_web import create_local_app
from mail2leads.store import repo
from mail2leads.store.db import connect
from mail2leads.tasks.extract_mail_facts import Extraction, validate


def test_grounding_rejects_invented_values_and_quotes():
    for value, quote in [("501 pcs", "500 pcs"), ("500 pcs", "Invented 500 pcs")]:
        with pytest.raises(ValueError):
            validate(
                Extraction(facts=[{"key": "quantity", "value": value, "quote": quote}]), "500 pcs"
            )


def test_queue_excludes_history_caches_results_and_preserves_original(tmp_path, monkeypatch):
    conn = connect(tmp_path / "test.sqlite3")
    mailbox = repo.ensure_mailbox(conn, "sales@example.test")
    pk, _ = store_raw(
        conn,
        mailbox,
        make_raw(body="500 pcs\n\nOn Monday, Joe wrote:\n> 900 pcs"),
        "in",
        datetime.now(UTC),
    )
    fact_store.prepare(conn)
    assert fact_store.get(conn, pk)["status"] == "queued"
    calls = []

    def extract(source):
        calls.append(source)
        assert "900 pcs" not in source
        return [{"key": "quantity", "value": "500 pcs", "quote": "500 pcs"}]

    monkeypatch.setattr(fact_store.task, "extract", extract)
    assert fact_store.process(conn, pk) == "ok"
    assert fact_store.get(conn, pk)["facts"][0]["value"] == "500 pcs"
    assert conn.execute("SELECT COUNT(*) FROM lead").fetchone()[0] == 0
    fact_store.prepare(conn)
    assert fact_store.counts(conn) == {"ok": 1}
    assert fact_store.process(conn, pk) == "ok"
    assert len(calls) == 1
    duplicate, _ = store_raw(
        conn,
        mailbox,
        make_raw(
            body="500 pcs\n\nOn Monday, Joe wrote:\n> 900 pcs", message_id="<other@example.test>"
        ),
        "in",
        datetime.now(UTC),
    )
    fact_store.prepare(conn)
    assert fact_store.process(conn, duplicate) == "ok"
    assert len(calls) == 1
    assert (
        "900 pcs" in conn.execute("SELECT body_quoted FROM message WHERE id=?", (pk,)).fetchone()[0]
    )
    conn.close()


def test_failed_extraction_is_not_empty_success(tmp_path, monkeypatch):
    conn = connect(tmp_path / "test.sqlite3")
    mailbox = repo.ensure_mailbox(conn, "sales@example.test")
    pk, _ = store_raw(conn, mailbox, make_raw(body="500 pcs"), "in", datetime.now(UTC))
    fact_store.prepare(conn)

    def fail(source):
        raise ValueError("private original should not leak into status")

    monkeypatch.setattr(fact_store.task, "extract", fail)
    assert fact_store.process(conn, pk) == "failed"
    result = fact_store.get(conn, pk)
    assert result["status"] == "failed" and result["facts"] == []
    assert "private original" not in result["reason"]
    conn.close()


def test_forward_shell_bootstraps_quoted_history_once(tmp_path, monkeypatch):
    conn = connect(tmp_path / "test.sqlite3")
    mailbox = repo.ensure_mailbox(conn, "sales@example.test")
    quote = "Customer needs 500 pcs SATA SSD. " * 20
    pk, _ = store_raw(
        conn,
        mailbox,
        make_raw(body="Get Outlook for Mac\n\nOn Tuesday, Jane wrote:\n> " + quote),
        "in",
        datetime.now(UTC),
    )
    fact_store.prepare(conn)
    seen = []
    monkeypatch.setattr(
        fact_store.task,
        "extract",
        lambda source: (
            seen.append(source) or [{"key": "quantity", "value": "500 pcs", "quote": "500 pcs"}]
        ),
    )
    assert fact_store.process(conn, pk) == "ok"
    assert seen and "Historical quoted content" in seen[0]
    result = fact_store.get(conn, pk)
    assert "引用历史首次提取" in result["coverage"]
    assert fact_store.process(conn, pk) == "ok"
    assert len(seen) == 1
    conn.close()


def test_pause_persists_across_restart(tmp_path):
    conn = connect(tmp_path / "mailbox.sqlite3")
    conn.close()
    with TestClient(create_local_app(tmp_path, automatic=True)) as client:
        assert client.get("/mail/extraction").json()["enabled"]
        assert not client.post("/mail/extraction/pause").json()["enabled"]
    with TestClient(create_local_app(tmp_path, automatic=True)) as client:
        assert not client.get("/mail/extraction").json()["enabled"]
        assert client.post("/mail/extraction/resume").json()["enabled"]
