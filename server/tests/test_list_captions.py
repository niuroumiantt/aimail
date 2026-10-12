"""Cached captions are scoped, recoverable, bounded and cannot alter original mail."""

import json
import threading
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from aimail import backends
from aimail.api.app import create_app
from aimail.store import list_captions, repo
from aimail.tasks.list_caption import Caption, Captions, generate
from test_mail_trash import incoming, snapshot


def test_cached_caption_survives_reopen_and_new_mail_invalidates_it(conn, mailbox):
    tid, pk, _ = incoming(conn, mailbox)
    before = snapshot(conn, ("thread", "message", "attachment"))
    jobs = list_captions.claim(conn, [tid], backend="local", model="fixture")
    assert list_captions.claim(conn, [tid], backend="local", model="fixture") == []
    list_captions.finish(conn, jobs, {tid: "服务器采购询价"})
    assert list_captions.get(conn, tid)["text_zh"] == "服务器采购询价"
    assert list_captions.claim(conn, [tid], backend="codex_cli", model="other") == []
    assert snapshot(conn, tuple(before)) == before
    # Later arriving original message invalidates this source's derived caption.
    incoming(
        conn,
        mailbox,
        "<reply@test>",
        in_reply_to="<news@sample.test>",
        body="More CPUs",
        date=datetime(2026, 10, 4, tzinfo=UTC),
    )
    assert list_captions.get(conn, tid) is None
    new = list_captions.claim(conn, [tid], backend="local", model="fixture")
    list_captions.finish(conn, jobs, {tid: "旧的描述"})
    assert list_captions.get(conn, tid)["status"] == "pending"
    list_captions.finish(conn, new, None)
    assert list_captions.claim(conn, [tid], backend="local", model="fixture") == []
    assert list_captions.claim(conn, [tid], backend="local", model="fixture", retry=True)


@pytest.mark.parametrize("text", ["English only", "中文\n换行", "文" * 49, ""])
def test_caption_requires_short_chinese_line(text):
    with pytest.raises(ValidationError):
        Caption(id=1, text_zh=text)


def test_model_batch_must_return_exact_requested_ids(monkeypatch):
    monkeypatch.setattr(
        backends, "complete", lambda *a, **kw: Captions(items=[Caption(id=999, text_zh="采购询价")])
    )
    with pytest.raises(backends.LLMError):
        generate([{"id": 1, "subject": "RFQ", "body": "Hello", "backend": "local"}])


def test_api_queues_once_does_not_block_reading_and_reuses_cache(conn, mailbox, monkeypatch):
    tid, _, _ = incoming(conn, mailbox)
    started, release = threading.Event(), threading.Event()
    calls = []
    monkeypatch.setattr(backends, "ready", lambda: (True, ""))

    def complete(system, user, shape, **kw):
        calls.append(json.loads(user))
        started.set()
        release.wait(2)
        return Captions(items=[Caption(id=tid, text_zh="服务器采购询价")])

    monkeypatch.setattr(backends, "complete", complete)
    client = TestClient(create_app(conn, mailbox))
    try:
        r = client.post("/api/list-captions", json={"ids": [tid]})
        assert r.status_code == 200 and r.json()[str(tid)]["status"] == "pending"
        assert started.wait(1)
        assert client.get("/api/threads").status_code == 200
        assert client.post("/api/list-captions", json={"ids": [tid]}).status_code == 200
    finally:
        release.set()
    for _ in range(100):
        data = client.get(f"/api/list-captions?ids={tid}").json()
        if data[str(tid)]["status"] == "ok":
            break
        time.sleep(0.01)
    assert data[str(tid)]["text_zh"] == "服务器采购询价"
    monkeypatch.setattr(backends, "ready", lambda: (False, "offline"))
    assert client.post("/api/list-captions", json={"ids": [tid]}).status_code == 200
    assert len(calls) == 1
    other = repo.ensure_mailbox(conn, "private@example.test")
    private, _, _ = incoming(conn, other, "<private@test>")
    assert client.post("/api/list-captions", json={"ids": [tid, private]}).status_code == 404
    assert client.get(f"/api/list-captions?ids={private}").status_code == 404
    assert list_captions.get(conn, private) is None


@pytest.mark.parametrize("text", ["采购 9999 台服务器", "DDR6 内存询价"])
def test_caption_cannot_invent_numbers_or_identifiers(monkeypatch, text):
    monkeypatch.setattr(
        backends, "complete", lambda *a, **kw: Captions(items=[Caption(id=1, text_zh=text)])
    )
    with pytest.raises(backends.LLMError, match="数字或型号"):
        generate(
            [
                {
                    "id": 1,
                    "subject": "RFQ DDR5",
                    "body": "Please quote 32 memory modules",
                    "backend": "local",
                }
            ]
        )


def test_saved_caption_and_expired_job_recover_across_database_reopen(tmp_path):
    from aimail.store.db import connect

    db = tmp_path / "mail.sqlite"
    conn = connect(db)
    mailbox = repo.ensure_mailbox(conn, "sales@example.test")
    tid, _, _ = incoming(conn, mailbox)
    jobs = list_captions.claim(conn, [tid], backend="local", model="fixture")
    conn.execute("UPDATE mail_list_caption SET produced_at='2020-01-01T00:00:00+00:00'")
    conn.close()
    conn = connect(db)
    fresh = list_captions.claim(conn, [tid], backend="local", model="fixture")
    assert fresh and fresh[0]["token"] != jobs[0]["token"]
    list_captions.finish(conn, fresh, {tid: "采购询价"})
    conn.close()
    conn = connect(db)
    assert list_captions.get(conn, tid)["text_zh"] == "采购询价"
    assert list_captions.claim(conn, [tid], backend="local", model="fixture") == []
    conn.close()
