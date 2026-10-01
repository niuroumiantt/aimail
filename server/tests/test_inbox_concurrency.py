"""Browsing committed mail must not wait for an IMAP or AI network operation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event

import pytest
from fastapi.testclient import TestClient

from aimail.api.app import create_app
from aimail.ingest.run import store_raw
from aimail.store import repo
from aimail.store.db import connect
from conftest import make_raw


@pytest.mark.parametrize("operation", ["sync", "analyze"])
def test_browse_while_network_operation_waits(tmp_path, monkeypatch, operation):
    conn = connect(tmp_path / "mail ? snapshot.db")
    sales = repo.ensure_mailbox(conn, "sales@example.test")
    private = repo.ensure_mailbox(conn, "private@example.test")
    tids = []
    for box, subject in ((sales, "Sales RFQ"), (private, "Private note")):
        pk, _ = store_raw(
            conn,
            box,
            make_raw(subject=subject, message_id=f"<{box}@test>"),
            "in",
            datetime.now(UTC),
        )
        tids.append(conn.execute("SELECT thread_id FROM message WHERE id = ?", (pk,)).fetchone()[0])
    entered, release = Event(), Event()

    def slow_network(*args, **kwargs):
        entered.set()
        assert release.wait(10), "test did not release the simulated network request"

    monkeypatch.setattr("aimail.api.app.backends.ready", lambda: (True, ""))
    monkeypatch.setattr("aimail.api.app.read_message", slow_network)
    app = create_app(
        conn,
        sales,
        require_oa_auth=True,
        mailbox_access={"owner@example.test": ("sales@example.test", "private@example.test")},
        sync_mailbox=slow_network,
    )
    owner = {"X-OA-Email": "owner@example.test", "X-OA-User": "Owner"}
    path = "/api/sync" if operation == "sync" else f"/api/threads/{tids[0]}/analyze"

    def browse(client):
        for address, subject, tid in zip(
            ("sales@example.test", "private@example.test"),
            ("Sales RFQ", "Private note"),
            tids,
            strict=True,
        ):
            headers = {**owner, "X-Mailbox-Address": address}
            assert client.get("/api/mailbox", headers=headers).json()["address"] == address
            assert [t["subject"] for t in client.get("/api/threads", headers=headers).json()] == [
                subject
            ]
            assert client.get(f"/api/threads/{tid}", headers=headers).json()["messages"]
        assert len(client.get("/api/mailboxes", headers=owner).json()["items"]) == 2
        employee = {"X-OA-Email": "sales@example.test", "X-Mailbox-Address": "private@example.test"}
        assert client.get("/api/threads", headers=employee).status_code == 403
        assert (
            client.get(
                f"/api/threads/{tids[1]}", headers={"X-OA-Email": "sales@example.test"}
            ).status_code
            == 404
        )
        assert client.get("/api/threads").status_code == 401

    try:
        with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as pool:
            waiting = pool.submit(client.post, path, headers=owner)
            try:
                assert entered.wait(3)
                # Completes BEFORE releasing IMAP/AI, not a fragile latency benchmark.
                pool.submit(browse, client).result(timeout=3)
                assert not waiting.done()
            finally:
                release.set()
            assert waiting.result(timeout=3).status_code == 200
    finally:
        conn.close()
