"""API 的形状要和 web/src/data/types.ts 对得上;错的 ID 要 404。"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from conftest import make_raw
from mail2leads.api.app import create_app
from mail2leads.ingest.run import store_raw

NOW = datetime(2026, 9, 19, tzinfo=UTC)


def _client(conn, mailbox):
    store_raw(
        conn,
        mailbox,
        make_raw(
            message_id="<1@x>",
            subject="RFQ 2U",
            body="We need 48 units.",
            attachments=[("spec.pdf", b"%PDF", "application/pdf")],
        ),
        "in",
        NOW,
    )
    store_raw(
        conn,
        mailbox,
        make_raw(
            message_id="<2@x>",
            subject="Re: RFQ 2U",
            in_reply_to="<1@x>",
            body="Still available?\n\nOn x wrote:\n> We need 48 units.",
        ),
        "in",
        NOW,
    )
    return TestClient(create_app(conn, mailbox))


def test_thread_list_has_the_web_shape(conn, mailbox):
    client = _client(conn, mailbox)
    threads = client.get("/api/threads").json()
    assert len(threads) == 1
    t = threads[0]
    for key in (
        "id",
        "subject",
        "company",
        "contact",
        "email",
        "region",
        "scale",
        "folder",
        "updated_at",
        "messages",
        "reading",
    ):
        assert key in t, key
    assert t["folder"] == "inbox"
    assert t["reading"] is None


def test_thread_detail_carries_messages_quoted_and_attachments(conn, mailbox):
    client = _client(conn, mailbox)
    tid = client.get("/api/threads").json()[0]["id"]
    t = client.get(f"/api/threads/{tid}").json()
    assert [m["body"] for m in t["messages"]] == ["We need 48 units.", "Still available?"]
    assert t["messages"][1]["quoted"].startswith("On x wrote:")
    assert t["messages"][0]["attachments"] == ["spec.pdf"]


def test_unknown_thread_is_404(conn, mailbox):
    assert _client(conn, mailbox).get("/api/threads/9999").status_code == 404


def test_folder_filter(conn, mailbox):
    client = _client(conn, mailbox)
    assert client.get("/api/threads?folder=quote").json() == []
    assert len(client.get("/api/threads?folder=inbox").json()) == 1
