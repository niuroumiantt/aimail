"""API 的形状要和 web/src/data/types.ts 对得上;错的 ID 要 404。"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from conftest import make_raw
from mail2leads.api.app import create_app
from mail2leads.ingest.run import store_raw
from mail2leads.store import repo

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
    assert [a["name"] for a in t["messages"][0]["attachments"]] == ["spec.pdf"]


def test_unknown_thread_is_404(conn, mailbox):
    assert _client(conn, mailbox).get("/api/threads/9999").status_code == 404


def test_oa_auth_mode_accepts_only_the_portal_identity(conn, mailbox):
    client = TestClient(create_app(conn, mailbox, require_oa_auth=True))
    # 这里用一个写接口验证身份头；X-User 在 OA 模式下不能伪造审计人。
    assert (
        client.post("/api/leads/suggestions/1/dismiss", headers={"X-User": "Mallory"}).status_code
        == 401
    )
    assert (
        client.post(
            "/api/leads/suggestions/1/dismiss",
            headers={"X-OA-User": "Alice", "X-OA-Email": "sales@example.test"},
        ).status_code
        == 404
    )


def test_owner_can_switch_mailboxes_but_other_users_cannot(conn, mailbox):
    other = repo.ensure_mailbox(conn, "larry@example.test", "Larry")

    def _seed(mid, subject):
        return store_raw(
            conn,
            mid,
            make_raw(message_id=f"<{subject}@x>", subject=subject, body=subject),
            "in",
            NOW,
        )

    _seed(mailbox, "Sales RFQ")
    _seed(other, "Private note")
    client = TestClient(
        create_app(
            conn,
            other,
            require_oa_auth=True,
            mailbox_access={"larry@example.test": ("sales@example.test", "larry@example.test")},
            mailbox_tasks={
                "sales@example.test": frozenset({"read", "leads"}),
                "larry@example.test": frozenset({"read"}),
            },
        )
    )
    owner = {"X-OA-Email": "larry@example.test", "X-OA-User": "Larry"}
    boxes = client.get("/api/mailboxes", headers=owner).json()
    assert [x["address"] for x in boxes["items"]] == ["sales@example.test", "larry@example.test"]
    assert boxes["default"] == "sales@example.test"
    assert [x["subject"] for x in client.get("/api/threads", headers=owner).json()] == ["Sales RFQ"]
    private = {**owner, "X-Mailbox-Address": "larry@example.test"}
    assert [x["subject"] for x in client.get("/api/threads", headers=private).json()] == [
        "Private note"
    ]
    employee = {"X-OA-Email": "sales@example.test", "X-OA-User": "Sales"}
    forbidden = client.get(
        "/api/threads", headers={**employee, "X-Mailbox-Address": "larry@example.test"}
    )
    assert forbidden.status_code == 403


def test_folder_filter(conn, mailbox):
    client = _client(conn, mailbox)
    assert client.get("/api/threads?folder=quote").json() == []
    assert len(client.get("/api/threads?folder=inbox").json()) == 1


def test_production_assistant_is_mailbox_scoped_and_reports_missing_model(conn, mailbox):
    other = repo.ensure_mailbox(conn, "private@example.test")
    client = TestClient(
        create_app(
            conn,
            mailbox,
            require_oa_auth=True,
            mailbox_access={"owner@example.test": ("sales@example.test", "private@example.test")},
        )
    )
    owner = {"X-OA-Email": "owner@example.test", "X-OA-User": "Owner"}
    state = client.get("/api/assistant", headers=owner).json()
    assert state["configured"] is False
    assert state["mailbox"] == "sales@example.test"
    assert (
        client.post("/api/assistant", headers=owner, json={"question": "RFQ?"}).status_code == 503
    )
    private = {**owner, "X-Mailbox-Address": "private@example.test"}
    assert client.get("/api/assistant", headers=private).json()["mailbox"] == "private@example.test"
    assert other != mailbox


def test_production_assistant_returns_checked_sources(conn, mailbox, monkeypatch):
    client = _client(conn, mailbox)
    monkeypatch.setattr("mail2leads.backends.ready", lambda: (True, "ok"))
    monkeypatch.setattr("mail2leads.backends.describe", lambda *_: "Test model")

    def answer(question, sources, history):
        assert question == "哪些询价？"
        assert len(sources) == 2
        assert history == []
        return [
            {
                "text": "客户正在询价。",
                "quote": "Still available?",
                "source_id": sources[0]["id"],
                "thread_id": sources[0]["thread_id"],
                "subject": sources[0]["subject"],
                "unverified": [],
            }
        ]

    monkeypatch.setattr("mail2leads.tasks.ask_mailbox.ask", answer)
    headers = {"X-User": "Larry"}
    response = client.post("/api/assistant", headers=headers, json={"question": "哪些询价？"})
    assert response.status_code == 200
    turn = response.json()["turns"][0]
    assert turn["status"] == "done"
    assert turn["findings"][0]["quote"] == "Still available?"
    assert client.post("/api/assistant/clear", headers=headers).json()["turns"] == []
    assert conn.execute("SELECT COUNT(*) FROM mailbox_assistant_event").fetchone()[0] == 3


def test_spa_fallback_serves_index_and_assets(conn, mailbox, tmp_path):
    """部署时前端由 API 托管:深链接回 index.html,静态资源按路径给;API 路径不被兜底吞掉。"""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id=root></div>", "utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", "utf-8")
    client = TestClient(create_app(conn, mailbox, web_dist=dist))
    assert client.get("/t/123").text == "<div id=root></div>"
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/api/threads/9999").status_code == 404
    assert client.get("/healthz").json() == {"ok": True}
