"""攻击 M8:下游只凭接口拿事实——机器令牌只能读,建议永远不出门;
推送有签名、有回执、失败可见、永不丢。"""

from __future__ import annotations

import http.server
import json
import socket
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
import uvicorn
from fastapi.testclient import TestClient

from conftest import make_raw
from mail2leads.api.app import CSV_COLUMNS, create_app
from mail2leads.config import parse_tokens
from mail2leads.ingest.run import store_raw
from mail2leads.store import leads, outbox, repo

NOW = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
TOKEN = "oa-0123456789abcdef0123456789abcdef"
TOKENS = {"oa": TOKEN}
BEARER = {"Authorization": f"Bearer {TOKEN}"}

# 这就是合同:改任何一个键都要先写 ADR,再改这里
LEAD_V1_KEYS = [
    "company",
    "confirmed_at",
    "confirmed_by",
    "contact",
    "email",
    "id",
    "next_step",
    "quantity",
    "region",
    "source",
    "status",
    "updated_at",
    "version",
    "wants",
]


def soon(offset: int = 1) -> datetime:
    """事件按真实时间入队;投递的"现在"要取在入队之后,而且要在用它的那个测试里取。"""
    return (datetime.now(UTC) + timedelta(seconds=offset)).replace(microsecond=0)


def _suggestion(conn, mailbox, *, message_id="<s@x>", company="Aurora") -> int:
    pk, _ = store_raw(
        conn,
        mailbox,
        make_raw(message_id=message_id, subject=f"RFQ {company}", body="We need 48 units."),
        "in",
        NOW,
    )
    tid = int(conn.execute("SELECT thread_id FROM message WHERE id = ?", (pk,)).fetchone()[0])
    return leads.insert_suggestion(
        conn,
        pk,
        tid,
        "Spark · fast",
        "extract_lead@1",
        NOW.isoformat(),
        {
            "company": company,
            "contact": "Mikko",
            "wants": "2U servers",
            "quantity": "48",
            "region": "Helsinki",
            "priority": "high",
            "quoted_numbers": ["48"],
            "unverified": [],
        },
    )


class FakePoster:
    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.calls: list[tuple[bytes, dict[str, str]]] = []

    def post(self, body: bytes, headers: dict[str, str]) -> tuple[int, str]:
        self.calls.append((body, headers))
        return self.status, "ok" if self.status < 300 else "nope"


# ── 机器只能读,读的只有事实 ──


def test_v1_leads_requires_a_machine_token(conn, mailbox):
    client = TestClient(create_app(conn, mailbox, api_tokens=TOKENS))
    assert client.get("/v1/leads").status_code == 401
    assert client.get("/v1/leads", headers={"X-User": "Larry"}).status_code == 401  # 人也不算机器
    assert client.get("/v1/leads", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/v1/leads", headers=BEARER).status_code == 200


def test_v1_returns_only_confirmed_facts_never_suggestions(conn, mailbox):
    sid = _suggestion(conn, mailbox)
    client = TestClient(create_app(conn, mailbox, api_tokens=TOKENS))
    assert client.get("/v1/leads", headers=BEARER).json()["leads"] == []  # 建议不出门
    leads.confirm(conn, sid, "Larry")
    got = client.get("/v1/leads", headers=BEARER).json()
    assert got["version"] == "v1" and [lead["company"] for lead in got["leads"]] == ["Aurora"]
    lead = got["leads"][0]
    assert sorted(lead) == LEAD_V1_KEYS and lead["version"] == "lead@1"
    assert lead["email"] == "mikko@aurora.test" and lead["source"]["subject"] == "RFQ Aurora"
    assert sorted(lead["source"]) == ["mailbox", "subject", "thread_id"]


def test_machine_token_cannot_confirm_or_edit_leads(conn, mailbox):
    sid = _suggestion(conn, mailbox)
    client = TestClient(create_app(conn, mailbox, api_tokens=TOKENS))
    assert client.post(f"/api/leads/suggestions/{sid}/confirm", headers=BEARER).status_code == 401
    lead_id = leads.confirm(conn, sid, "Larry")
    patched = client.patch(f"/api/leads/{lead_id}", json={"status": "won"}, headers=BEARER)
    assert patched.status_code == 401
    assert conn.execute("SELECT status FROM lead").fetchone()[0] == "quote"


def test_v1_since_cursor_status_filter_and_mailbox_isolation(conn, mailbox):
    # 两条在同一秒确认:靠时间戳分不开,游标必须靠 id 接着翻
    a = leads.confirm(conn, _suggestion(conn, mailbox, message_id="<a@x>", company="A"), "Larry")
    b = leads.confirm(conn, _suggestion(conn, mailbox, message_id="<b@x>", company="B"), "Larry")
    other = repo.ensure_mailbox(conn, "other@example.test", "Other")
    leads.confirm(conn, _suggestion(conn, other, message_id="<c@x>", company="C"), "Larry")
    client = TestClient(create_app(conn, mailbox, api_tokens=TOKENS))
    page = client.get("/v1/leads", headers=BEARER).json()
    assert [lead["id"] for lead in page["leads"]] == [str(a), str(b)]  # C 在别的邮箱,看不见
    assert page["next_since"] == page["leads"][-1]["updated_at"]
    assert page["next_after"] == b
    first = client.get("/v1/leads", params={"limit": 1}, headers=BEARER).json()
    assert [lead["id"] for lead in first["leads"]] == [str(a)]
    cursor = {"since": first["next_since"], "after": first["next_after"]}
    later = client.get("/v1/leads", params=cursor, headers=BEARER).json()
    assert [lead["id"] for lead in later["leads"]] == [str(b)]
    cursor = {"since": later["next_since"], "after": later["next_after"]}
    assert client.get("/v1/leads", params=cursor, headers=BEARER).json()["leads"] == []
    leads.update_lead(conn, a, "Larry", status="won")
    won = client.get("/v1/leads", params={"status": "won"}, headers=BEARER).json()["leads"]
    assert [lead["id"] for lead in won] == [str(a)]
    assert client.get("/v1/leads", params={"status": "bogus"}, headers=BEARER).status_code == 422


def test_csv_export_has_one_row_per_lead_and_survives_commas(conn, mailbox):
    sid = _suggestion(conn, mailbox)
    leads.confirm(conn, sid, "Larry", {"wants": 'Servers, "2U", rails'})
    client = TestClient(create_app(conn, mailbox, api_tokens=TOKENS))
    assert client.get("/v1/leads.csv").status_code == 401
    r = client.get("/v1/leads.csv", headers=BEARER)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.lstrip("﻿").splitlines()
    assert lines[0] == ",".join(CSV_COLUMNS) and len(lines) == 2
    assert '"Servers, ""2U"", rails"' in lines[1]
    assert client.get("/api/leads.csv").text == r.text  # 界面的导出按钮走同一份


# ── 推送 ──


def test_confirm_and_update_enqueue_events_atomically(conn, mailbox):
    lead_id = leads.confirm(conn, _suggestion(conn, mailbox), "Larry")
    leads.update_lead(conn, lead_id, "Larry", status="quoted")
    events = conn.execute("SELECT event, lead_id, payload FROM outbox ORDER BY id").fetchall()
    assert [(e["event"], e["lead_id"]) for e in events] == [
        ("lead.confirmed", lead_id),
        ("lead.updated", lead_id),
    ]
    assert json.loads(events[1]["payload"])["status"] == "quoted"
    with pytest.raises(LookupError):
        leads.update_lead(conn, 999, "Larry", status="won")
    assert conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 2  # 失败的更新不留事件


def test_delivery_is_signed_and_marked_delivered(conn, mailbox):
    lead_id = leads.confirm(conn, _suggestion(conn, mailbox), "Larry")
    t = soon()
    poster = FakePoster()
    assert outbox.deliver_pending(conn, mailbox, poster, "s3cret", t) == (1, 0)
    body, headers = poster.calls[0]
    assert outbox.verify("s3cret", body, headers["X-Mail2leads-Signature"])
    assert not outbox.verify("other", body, headers["X-Mail2leads-Signature"])
    sent = json.loads(body)
    assert sent["event"] == "lead.confirmed" and sent["lead"]["id"] == str(lead_id)
    assert headers["X-Mail2leads-Delivery"] == sent["delivery"]
    row = conn.execute("SELECT * FROM outbox").fetchone()
    assert row["delivered_at"] == t.isoformat() and row["attempts"] == 1
    assert outbox.deliver_pending(conn, mailbox, poster, "s3cret", t) == (0, 0)  # 不重复送


def test_delivery_never_crosses_mailbox_boundaries(conn, mailbox):
    """共用一个 SQLite 文件时，每个实例也只能向自己的下游投递。"""
    other_mailbox = repo.ensure_mailbox(conn, "support@example.test")
    first = _suggestion(conn, mailbox, message_id="<sales@x>", company="Sales")
    second = _suggestion(conn, other_mailbox, message_id="<support@x>", company="Support")
    leads.confirm(conn, first, "Larry")
    leads.confirm(conn, second, "Larry")
    poster = FakePoster()
    assert outbox.deliver_pending(conn, mailbox, poster, "s3cret", soon()) == (1, 0)
    assert len(poster.calls) == 1
    assert json.loads(poster.calls[0][0])["lead"]["company"] == "Sales"
    assert outbox.status(conn, other_mailbox)["pending"] == 1


def test_failed_delivery_backs_off_and_stays_visible(conn, mailbox):
    leads.confirm(conn, _suggestion(conn, mailbox), "Larry")
    t = soon()
    poster = FakePoster(status=503)
    assert outbox.deliver_pending(conn, mailbox, poster, "s", t) == (0, 1)
    row = conn.execute("SELECT * FROM outbox").fetchone()
    assert row["delivered_at"] is None and row["attempts"] == 1
    assert row["next_at"] == (t + timedelta(seconds=60)).isoformat()
    assert row["last_error"].startswith("HTTP 503")
    assert outbox.deliver_pending(conn, mailbox, poster, "s", t + timedelta(seconds=30)) == (
        0,
        0,
    )  # 没到点
    assert outbox.deliver_pending(conn, mailbox, poster, "s", t + timedelta(seconds=61)) == (0, 1)
    assert (
        conn.execute("SELECT next_at FROM outbox").fetchone()[0]
        == (t + timedelta(seconds=61 + 300)).isoformat()
    )
    client = TestClient(create_app(conn, mailbox, webhook_configured=True))
    seen = client.get("/api/outbox").json()
    assert seen["configured"] and seen["failed"] == 1 and "503" in seen["last_error"]
    assert TestClient(create_app(conn, mailbox)).get("/api/outbox").json()["configured"] is False


def test_network_error_is_a_recorded_failure_not_a_crash(conn, mailbox):
    leads.confirm(conn, _suggestion(conn, mailbox), "Larry")
    t = soon()

    class Boom:
        def post(self, body, headers):
            raise ConnectionError("no route")

    assert outbox.deliver_pending(conn, mailbox, Boom(), "s", t) == (0, 1)
    assert "ConnectionError" in conn.execute("SELECT last_error FROM outbox").fetchone()[0]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_real_http_delivery_end_to_end(conn, mailbox):
    """真的走一遍 HTTP:下游用同一个 secret 验签,验不过就 400。"""
    received: list[dict] = []

    class Hook(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            ok = outbox.verify("s3cret", body, self.headers.get("X-Mail2leads-Signature", ""))
            received.append({"ok": ok, "event": self.headers.get("X-Mail2leads-Event")})
            self.send_response(200 if ok else 400)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Hook)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        leads.confirm(conn, _suggestion(conn, mailbox), "Larry")
        t = soon()
        url = f"http://127.0.0.1:{server.server_port}/hook"
        assert outbox.deliver_pending(conn, mailbox, outbox.HttpPoster(url), "wrong", t) == (0, 1)
        assert received[-1]["ok"] is False
        assert outbox.deliver_pending(
            conn, mailbox, outbox.HttpPoster(url), "s3cret", t + timedelta(61)
        )
        assert received[-1] == {"ok": True, "event": "lead.confirmed"}
    finally:
        server.shutdown()


def test_pull_leads_script_gets_confirmed_leads_over_http_with_only_a_token(conn, mailbox):
    """验收:一个外部脚本只凭接口拿到确认过的线索。"""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "pull_leads", Path(__file__).resolve().parents[2] / "examples" / "pull_leads.py"
    )
    assert spec and spec.loader
    pull = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pull)

    leads.confirm(conn, _suggestion(conn, mailbox), "Larry")
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(conn, mailbox, api_tokens=TOKENS),
            host="127.0.0.1",
            port=port,
            log_level="error",
        )
    )
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        data = pull.fetch(f"http://127.0.0.1:{port}", TOKEN)
        assert [lead["company"] for lead in data["leads"]] == ["Aurora"]
        with pytest.raises(Exception, match="401"):
            pull.fetch(f"http://127.0.0.1:{port}", "not-the-token")
    finally:
        server.should_exit = True


def test_token_parsing_rejects_short_or_nameless_tokens():
    assert parse_tokens("oa:0123456789abcdef, po:fedcba9876543210x") == {
        "oa": "0123456789abcdef",
        "po": "fedcba9876543210x",
    }
    with pytest.raises(RuntimeError):
        parse_tokens("0123456789abcdef")
    with pytest.raises(RuntimeError):
        parse_tokens("oa:short")
    assert parse_tokens("") == {}
