"""Browsing committed mail must not wait for an IMAP or AI network operation."""

import threading
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from datetime import UTC, datetime
from threading import Event
from types import SimpleNamespace

import anyio
import pytest
from fastapi.testclient import TestClient

from aimail.api.app import create_app
from aimail.ingest.run import store_raw
from aimail.store import repo
from aimail.store.db import connect
from conftest import make_raw


@pytest.fixture
def observe_write_waiters(monkeypatch):
    marker = ContextVar("synthetic_write", default="")
    attempted = {name: Event() for name in ("holder", "queued1", "queued2", "queued3", "other")}
    lock = threading.Lock()

    class ObservedLock:
        def acquire(self, *args, **kwargs):
            # Observe real acquisition attempts without changing lock behavior.
            if event := attempted.get(marker.get()):
                event.set()
            return lock.acquire(*args, **kwargs)

        def release(self):
            lock.release()

    monkeypatch.setattr(
        "aimail.api.app.threading", SimpleNamespace(Lock=ObservedLock, Thread=threading.Thread)
    )

    def install(app):
        @app.middleware("http")
        async def mark_request(request, call_next):
            token = marker.set(request.headers.get("X-Synthetic-Write", ""))
            try:
                return await call_next(request)
            finally:
                marker.reset(token)

    return install, attempted


def test_queued_writes_keep_read_routes_available_and_serialize_across_client_loops(
    tmp_path, monkeypatch, observe_write_waiters
):
    conn = connect(tmp_path / "synthetic.sqlite3")
    mailbox = repo.ensure_mailbox(conn, "sales@example.test")
    conn.execute("CREATE TABLE synthetic_write (sequence INTEGER PRIMARY KEY)")
    entered, release = Event(), Event()
    state_lock = threading.Lock()
    state = {"calls": 0, "active": 0, "max_active": 0}

    def slow_sync():
        with state_lock:
            state["calls"] += 1
            sequence = state["calls"]
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        entered.set()
        try:
            assert release.wait(10), "synthetic sync was not released"
            conn.execute("INSERT INTO synthetic_write VALUES (?)", (sequence,))
        finally:
            with state_lock:
                state["active"] -= 1

    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL", "synthetic")
    monkeypatch.setattr("aimail.api.app.backends.provider_catalog", lambda: [])
    monkeypatch.setattr(
        "aimail.api.app.backends.complete", lambda *args, **kwargs: pytest.fail("Model call")
    )
    app = create_app(conn, mailbox, sync_mailbox=slow_sync)
    install, attempted = observe_write_waiters
    install(app)

    def set_pool_size(size):
        limiter = anyio.to_thread.current_default_thread_limiter()
        previous = limiter.total_tokens
        limiter.total_tokens = size
        return previous

    def browse(client):
        assert client.get("/healthz").json() == {"ok": True}
        assert client.get("/api/threads").json() == []
        assert client.get("/api/model-selection").json()["selected"] == "local"

    try:
        with (
            TestClient(app) as client,
            TestClient(app) as other,
            ThreadPoolExecutor(max_workers=6) as pool,
        ):
            assert client.portal is not None
            original_tokens = client.portal.call(set_pool_size, 4)
            waiting = []
            try:
                waiting.append(
                    pool.submit(client.post, "/api/sync", headers={"X-Synthetic-Write": "holder"})
                )
                assert entered.wait(3)
                for marker in ("queued1", "queued2", "queued3"):
                    waiting.append(
                        pool.submit(client.post, "/api/sync", headers={"X-Synthetic-Write": marker})
                    )
                    assert attempted[marker].wait(3), "write request did not reach the shared lock"
                waiting.append(
                    pool.submit(other.post, "/api/sync", headers={"X-Synthetic-Write": "other"})
                )
                assert attempted["other"].wait(3)
                # Every waiter reached the real lock. Reads finish while sync is
                # still blocked, even at the smallest pool size that used to starve.
                pool.submit(browse, client).result(timeout=3)
                assert not release.is_set()
                assert all(not request.done() for request in waiting)
            finally:
                release.set()
                try:
                    for request in waiting:
                        assert request.result(timeout=3).status_code == 200
                finally:
                    client.portal.call(set_pool_size, original_tokens)
        assert state == {"calls": 5, "active": 0, "max_active": 1}
        assert [
            row[0] for row in conn.execute("SELECT sequence FROM synthetic_write ORDER BY sequence")
        ] == list(range(1, 6))
    finally:
        release.set()
        conn.close()


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
