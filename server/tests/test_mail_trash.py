"""回收站整理不能修改原文、越过邮箱权限或被重复同步撤销。"""

import sqlite3
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from aimail.api.app import create_app
from aimail.ingest.run import store_raw
from aimail.store import history, leads, mail_state, repo
from aimail.store.db import connect
from conftest import make_raw

NOW = datetime(2026, 10, 3, tzinfo=UTC)
PERSON = {"X-User": "Larry"}


def incoming(conn, mailbox, mid="<news@sample.test>", **kw):
    raw = make_raw(message_id=mid, **kw)
    pk, _ = store_raw(conn, mailbox, raw, "in", NOW)
    tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    return tid, pk, raw


def snapshot(conn, tables):
    return {table: [tuple(r) for r in conn.execute(f"SELECT * FROM {table}")] for table in tables}


def test_trash_restore_preserves_business_evidence_and_is_idempotent(conn, mailbox):
    tid, pk, _ = incoming(conn, mailbox, attachments=[("bill.txt", b"Bill", "text/plain")])
    sid = leads.insert_suggestion(
        conn,
        pk,
        tid,
        "fixture",
        "extract_lead@1",
        NOW.isoformat(),
        {"company": "Example", "wants": "Servers"},
    )
    leads.confirm(conn, sid, "Larry")
    repo.set_cursor(conn, mailbox, "INBOX", 1, 15)
    client = TestClient(create_app(conn, mailbox))
    tables = (
        "thread",
        "message",
        "attachment",
        "lead",
        "lead_suggestion",
        "outbox",
        "ingest_cursor",
        "followup",
        "reply_attempt",
        "outbound",
    )
    before = snapshot(conn, tables)
    first = client.post(f"/api/threads/{tid}/trash", headers=PERSON)
    assert first.status_code == 200
    assert first.json()["deleted_at"] and first.json()["has_lead"]
    assert client.post(f"/api/threads/{tid}/trash", headers=PERSON).json() == first.json()
    assert client.get("/api/threads").json() == []
    assert client.get("/api/threads?folder=quote").json() == []
    assert len(client.get("/api/threads?folder=trash").json()) == 1
    assert len(client.get("/api/threads?include_trash=true").json()) == 1
    assert client.get(f"/api/threads/{tid}").json()["messages"]
    assert snapshot(conn, tables) == before
    restored = client.post(f"/api/threads/{tid}/restore", headers=PERSON)
    assert restored.status_code == 200 and not restored.json()["deleted_at"]
    assert restored.json()["folder"] == "quote"
    assert client.post(f"/api/threads/{tid}/restore", headers=PERSON).status_code == 200
    assert len(client.get("/api/threads").json()) == 1
    assert client.get("/api/threads?folder=trash").json() == []
    assert snapshot(conn, tables) == before
    assert [tuple(r) for r in conn.execute("SELECT action,actor FROM thread_mail_event")] == [
        ("trash", "Larry"),
        ("restore", "Larry"),
    ]
    for operation in ("DELETE FROM", "UPDATE"):
        sql = f"{operation} thread_mail_event" + (
            " SET actor='changed'" if operation == "UPDATE" else ""
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql)


@pytest.mark.parametrize("action", ["trash", "restore"])
def test_trash_requires_person_and_selected_mailbox_authorization(conn, action):
    a = repo.ensure_mailbox(conn, "sales@example.test")
    b = repo.ensure_mailbox(conn, "private@example.test")
    ta, _, _ = incoming(conn, a, "<a@test>")
    tb, _, _ = incoming(conn, b, "<b@test>")
    mail_state.change(conn, ta, "trash", "setup")
    mail_state.change(conn, tb, "trash", "setup")
    client = TestClient(
        create_app(
            conn,
            a,
            require_oa_auth=True,
            mailbox_access={"owner@example.test": ("sales@example.test", "private@example.test")},
        )
    )
    owner = {"X-OA-Email": "owner@example.test", "X-OA-User": "Owner"}
    employee = {"X-OA-Email": "sales@example.test", "X-OA-User": "Sales"}
    before = snapshot(conn, ("thread_mail_state", "thread_mail_event"))
    assert client.post(f"/api/threads/{tb}/{action}").status_code == 401
    assert client.post(f"/api/threads/{tb}/{action}", headers=PERSON).status_code == 401
    assert client.post(f"/api/threads/{tb}/{action}", headers=employee).status_code == 404
    assert (
        client.post(
            f"/api/threads/{tb}/{action}",
            headers={**employee, "X-Mailbox-Address": "private@example.test"},
        ).status_code
        == 403
    )
    assert client.post(f"/api/threads/{tb}/{action}", headers=owner).status_code == 404
    assert snapshot(conn, ("thread_mail_state", "thread_mail_event")) == before
    assert (
        client.post(
            f"/api/threads/{tb}/{action}",
            headers={**owner, "X-Mailbox-Address": "private@example.test"},
        ).status_code
        == 200
    )


def test_new_reply_restores_thread_but_duplicate_ingest_does_not(conn, mailbox):
    tid, _, raw = incoming(conn, mailbox)
    mail_state.change(conn, tid, "trash", "Larry")
    assert store_raw(conn, mailbox, raw, "in", NOW)[0] is None
    assert mail_state.deleted_at(conn, tid)
    outgoing = make_raw(message_id="<out@sample.test>", in_reply_to="<news@sample.test>")
    store_raw(conn, mailbox, outgoing, "out", NOW)
    assert mail_state.deleted_at(conn, tid)
    replied, _, _ = incoming(conn, mailbox, "<reply@sample.test>", in_reply_to="<news@sample.test>")
    assert replied == tid and not mail_state.deleted_at(conn, tid)
    assert [r[0] for r in conn.execute("SELECT action FROM thread_mail_event")] == [
        "trash",
        "new_message",
    ]


def test_reopen_is_additive_and_trash_survives_restart(tmp_path):
    path = tmp_path / "old.db"
    conn = connect(path)
    mailbox = repo.ensure_mailbox(conn, "sales@example.test")
    tid, _, _ = incoming(conn, mailbox)
    # 模拟升级前没有新增表的数据库；原文、进度、游标保留。
    conn.execute("DROP TABLE thread_mail_state")
    conn.execute("DROP TABLE thread_mail_event")
    before = snapshot(conn, ("thread", "message", "ingest_cursor"))
    conn.close()
    for _ in range(2):
        conn = connect(path)
        assert snapshot(conn, ("thread", "message", "ingest_cursor")) == before
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        conn.close()
    conn = connect(path)
    mail_state.change(conn, tid, "trash", "Larry")
    conn.close()
    conn = connect(path)
    client = TestClient(create_app(conn, mailbox))
    assert client.get("/api/threads").json() == []
    assert client.get("/api/threads?folder=trash").json()[0]["id"] == str(tid)
    conn.close()


def test_deleted_threads_excluded_from_related_history_and_new_ai_evidence(
    conn, mailbox, monkeypatch
):
    old, _, _ = incoming(conn, mailbox, subject="Advertisement")
    new, _, _ = incoming(conn, mailbox, "<new@test>", subject="Order")
    assert len(history.related_threads(conn, mailbox, new)) == 1
    mail_state.change(conn, old, "trash", "Larry")
    assert history.related_threads(conn, mailbox, new) == []
    captured = []
    monkeypatch.setattr("aimail.api.app.backends.ready", lambda: (True, ""))
    monkeypatch.setattr(
        "aimail.api.app.ask_mailbox.ask", lambda q, sources, h: captured.extend(sources) or []
    )
    client = TestClient(create_app(conn, mailbox))
    assert (
        client.post("/api/assistant", json={"question": "Summarize"}, headers=PERSON).status_code
        == 200
    )
    assert {s["thread_id"] for s in captured} == {new}
