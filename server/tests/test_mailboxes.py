"""攻击 M9:两个邮箱互不可见——同一个库、同一套代码,凭 id 也拿不到别的邮箱的任何东西;
任务表决定一个邮箱开什么,不开的入口就不存在。"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from conftest import make_raw
from mail2leads import backends
from mail2leads.api.app import create_app
from mail2leads.config import parse_tasks
from mail2leads.ingest import attachments
from mail2leads.ingest.run import store_raw
from mail2leads.store import leads, repo
from mail2leads.tasks.read import read_message

NOW = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
TOKEN = "oa-0123456789abcdef0123456789abcdef"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
PERSON = {"X-User": "Larry"}


class FakeTransport:
    def deliver(self, sender, recipients, raw):
        return "ok"


def _suggest(conn, pk: int, tid: int) -> int:
    return leads.insert_suggestion(
        conn,
        pk,
        tid,
        "Spark · fast",
        "extract_lead@1",
        NOW.isoformat(),
        {
            "company": "X",
            "contact": "Y",
            "wants": "servers",
            "quantity": "48",
            "region": "",
            "priority": "normal",
            "quoted_numbers": [],
            "unverified": [],
        },
    )


def _seed(conn, mailbox: int, tag: str) -> dict[str, int]:
    """一个邮箱里各样东西各一份:线程、附件、一条待处理建议、一条确认过的线索。"""
    raw = make_raw(
        message_id=f"<{tag}@x>",
        subject=f"RFQ {tag}",
        body="We need 48 units.",
        attachments=[("spec.txt", b"BOM: 48 units", "text/plain")],
    )
    pk, _ = store_raw(conn, mailbox, raw, "in", NOW)
    assert pk is not None
    attachments.extract_for_message(conn, pk, NOW)
    tid = int(conn.execute("SELECT thread_id FROM message WHERE id = ?", (pk,)).fetchone()[0])
    att = int(conn.execute("SELECT id FROM attachment WHERE message_id = ?", (pk,)).fetchone()[0])
    lead_id = leads.confirm(conn, _suggest(conn, pk, tid), "Larry")
    return {
        "thread": tid,
        "attachment": att,
        "suggestion": _suggest(conn, pk, tid),
        "lead": lead_id,
    }


def test_everything_by_id_in_another_mailbox_is_invisible(conn):
    a = repo.ensure_mailbox(conn, "sales@example.test", "Sales")
    b = repo.ensure_mailbox(conn, "support@example.test", "Support")
    ia, ib = _seed(conn, a, "a"), _seed(conn, b, "b")
    app = TestClient(
        create_app(
            conn,
            a,
            sender="sales@example.test",
            transport=FakeTransport(),
            api_tokens={"oa": TOKEN},
            webhook_configured=True,
        )
    )
    # 列表只有自己的
    assert [t["subject"] for t in app.get("/api/threads").json()] == ["RFQ a"]
    assert [s["id"] for s in app.get("/api/leads/suggestions").json()] == [str(ia["suggestion"])]
    assert [x["id"] for x in app.get("/api/leads").json()] == [str(ia["lead"])]
    v1 = app.get("/v1/leads", headers=BEARER).json()["leads"]
    assert [x["id"] for x in v1] == [str(ia["lead"])]
    assert app.get("/api/mailbox").json()["address"] == "sales@example.test"
    # 凭 id 也拿不到 b 的任何东西
    tb, sb, lb, ab = ib["thread"], ib["suggestion"], ib["lead"], ib["attachment"]
    assert app.get(f"/api/threads/{tb}").status_code == 404
    assert app.get(f"/api/threads/{tb}/draft").status_code == 404
    assert app.post(f"/api/threads/{tb}/draft", headers=PERSON).status_code == 404
    assert app.post(f"/api/threads/{tb}/send-token", headers=PERSON).status_code == 404
    assert app.post(f"/api/leads/suggestions/{sb}/confirm", headers=PERSON).status_code == 404
    assert app.post(f"/api/leads/suggestions/{sb}/dismiss", headers=PERSON).status_code == 404
    assert app.patch(f"/api/leads/{lb}", json={"status": "won"}, headers=PERSON).status_code == 404
    assert app.get(f"/api/attachments/{ab}/text").status_code == 404
    # b 的东西一个字没动
    assert conn.execute("SELECT status FROM lead WHERE id = ?", (lb,)).fetchone()[0] == "quote"
    assert (
        conn.execute("SELECT status FROM lead_suggestion WHERE id = ?", (sb,)).fetchone()[0]
        == "open"
    )
    # 自己的照常;推送的账也只算自己的
    assert app.get(f"/api/threads/{ia['thread']}").status_code == 200
    patched = app.patch(f"/api/leads/{ia['lead']}", json={"status": "won"}, headers=PERSON)
    assert patched.status_code == 200
    assert app.get("/api/outbox").json()["pending"] == 2  # a 的确认 + 更新;b 的确认不算
    # 没身份的人先被拦在 401,不管 id 是谁的
    assert app.post(f"/api/leads/suggestions/{sb}/confirm").status_code == 401


def test_tasks_profile_turns_lead_suggestions_off(conn, mailbox, monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL", "fast")
    monkeypatch.setattr(
        backends,
        "_call_local",
        lambda s, u, h: json.dumps(
            {
                "is_inquiry": True,
                "detected_language": "en",
                "summary_zh": "要 48 台",
                "summary_en": "48 units",
                "facts": ["48 台"],
                "quoted_numbers": ["48"],
            }
        ),
    )
    pk, _ = store_raw(conn, mailbox, make_raw(message_id="<r@x>", body="48 units"), "in", NOW)
    assert read_message(conn, int(pk), tasks=frozenset({"read"})) == "ok"
    assert conn.execute("SELECT COUNT(*) FROM message_reading").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM lead_suggestion").fetchone()[0] == 0
    pk2, _ = store_raw(conn, mailbox, make_raw(message_id="<r2@x>", body="48 units"), "in", NOW)
    assert read_message(conn, int(pk2)) == "ok"  # 默认全开:提了(这里模型答非所问,记为 failed)
    assert conn.execute("SELECT COUNT(*) FROM lead_suggestion").fetchone()[0] == 1


def test_drafting_is_off_for_a_mailbox_that_only_reads(conn, mailbox):
    pk, _ = store_raw(conn, mailbox, make_raw(message_id="<d@x>"), "in", NOW)
    tid = int(conn.execute("SELECT thread_id FROM message WHERE id = ?", (pk,)).fetchone()[0])
    app = TestClient(create_app(conn, mailbox, tasks=frozenset({"read"}), display_name="Larry"))
    assert app.get("/api/mailbox").json() == {
        "address": "sales@example.test",
        "display_name": "Larry",
        "tasks": ["read"],
    }
    assert app.get(f"/api/threads/{tid}/draft").status_code == 404
    off = app.post(f"/api/threads/{tid}/draft", headers=PERSON)
    assert off.status_code == 404 and "没开起草" in off.json()["detail"]
    assert app.get(f"/api/threads/{tid}").status_code == 200  # 读还是读的


def test_tasks_env_is_validated():
    assert parse_tasks("") == frozenset({"read", "leads", "draft"})
    assert parse_tasks("leads") == frozenset({"read", "leads"})  # read 永远开
    with pytest.raises(RuntimeError):
        parse_tasks("read,bogus")
