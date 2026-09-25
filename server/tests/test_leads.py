"""攻击宪法第五条:建议不是事实。只有人能把建议变成线索;后台代码没有这条路。"""

from __future__ import annotations

import inspect
import itertools
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aimail import backends
from aimail.api.app import create_app
from aimail.ingest.run import store_raw
from aimail.store import leads
from aimail.tasks import read as read_mod
from aimail.tasks.read import read_message
from conftest import make_raw

NOW = datetime(2026, 9, 19, tzinfo=UTC)
SUMMARY = {
    "is_inquiry": True,
    "detected_language": "en",
    "summary_zh": "客户要 48 台。",
    "summary_en": "Customer needs 48 units.",
    "facts": ["48 台"],
    "quoted_numbers": ["48"],
}
LEAD = {
    "company": "Aurora Compute Oy",
    "contact": "Mikko Laine",
    "wants": "2U 机架服务器",
    "quantity": "48 units",
    "region": "Helsinki",
    "priority": "high",
    "quoted_numbers": ["48", "2U"],
}


@pytest.fixture(autouse=True)
def _local(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL", "fast")


def _answers(monkeypatch, *payloads):
    # 最后一个回答一直重复:模型"持续失败"时,改正的那一次也得有东西可回
    it = itertools.chain(payloads, itertools.repeat(payloads[-1]))
    monkeypatch.setattr(
        backends,
        "_call_local",
        lambda s, u, h: (lambda p: p if isinstance(p, str) else json.dumps(p, ensure_ascii=False))(
            next(it)
        ),
    )


def _read_one(
    conn, mailbox, monkeypatch, summary=SUMMARY, lead=LEAD, body="We need 48 units of 2U servers."
):
    _answers(monkeypatch, summary, lead)
    pk, _ = store_raw(conn, mailbox, make_raw(body=body), "in", NOW)
    read_message(conn, pk, NOW)
    return pk


def test_inquiry_reading_creates_an_open_suggestion_with_attribution(conn, mailbox, monkeypatch):
    _read_one(conn, mailbox, monkeypatch)
    rows = leads.open_suggestions(conn, mailbox)
    assert len(rows) == 1
    assert rows[0]["model"] == "Spark · fast" and rows[0]["task_version"] == "extract_lead@1"
    assert json.loads(rows[0]["payload"])["company"] == "Aurora Compute Oy"


def test_non_inquiry_creates_no_suggestion(conn, mailbox, monkeypatch):
    _read_one(
        conn, mailbox, monkeypatch, summary={**SUMMARY, "is_inquiry": False, "quoted_numbers": []}
    )
    assert leads.open_suggestions(conn, mailbox) == []


def test_failed_extraction_is_recorded_not_silent(conn, mailbox, monkeypatch):
    _read_one(conn, mailbox, monkeypatch, lead="不给 JSON")
    assert leads.open_suggestions(conn, mailbox) == []
    assert leads.failed_suggestions(conn, mailbox) == 1


def test_unverified_numbers_in_a_suggestion_are_kept(conn, mailbox, monkeypatch):
    _read_one(
        conn,
        mailbox,
        monkeypatch,
        lead={**LEAD, "quantity": "480 units", "quoted_numbers": ["480"]},
    )
    payload = json.loads(leads.open_suggestions(conn, mailbox)[0]["payload"])
    assert payload["unverified"] == ["480"]


def test_confirm_requires_a_person(conn, mailbox, monkeypatch):
    _read_one(conn, mailbox, monkeypatch)
    sid = int(leads.open_suggestions(conn, mailbox)[0]["id"])
    with pytest.raises(PermissionError):
        leads.confirm(conn, sid, "")
    with pytest.raises(PermissionError):
        leads.confirm(conn, sid, "   ")
    assert leads.list_leads(conn, mailbox) == []


def test_confirm_turns_suggestion_into_a_lead_and_moves_the_thread(conn, mailbox, monkeypatch):
    _read_one(conn, mailbox, monkeypatch)
    sid = int(leads.open_suggestions(conn, mailbox)[0]["id"])
    lead_id = leads.confirm(conn, sid, "Larry", {"quantity": "48 台"})
    lead = leads.list_leads(conn, mailbox)[0]
    assert int(lead["id"]) == lead_id
    assert (
        lead["confirmed_by"] == "Larry"
        and lead["quantity"] == "48 台"
        and lead["status"] == "quote"
    )
    assert leads.open_suggestions(conn, mailbox) == []
    assert conn.execute("SELECT folder FROM thread").fetchone()[0] == "quote"


def test_confirming_twice_is_rejected(conn, mailbox, monkeypatch):
    _read_one(conn, mailbox, monkeypatch)
    sid = int(leads.open_suggestions(conn, mailbox)[0]["id"])
    leads.confirm(conn, sid, "Larry")
    with pytest.raises(LookupError):
        leads.confirm(conn, sid, "Larry")
    assert len(leads.list_leads(conn, mailbox)) == 1


def test_dismiss_marks_the_suggestion_and_creates_no_lead(conn, mailbox, monkeypatch):
    _read_one(conn, mailbox, monkeypatch)
    sid = int(leads.open_suggestions(conn, mailbox)[0]["id"])
    leads.dismiss(conn, sid, "Larry")
    assert leads.open_suggestions(conn, mailbox) == []
    assert leads.list_leads(conn, mailbox) == []
    assert leads.get_suggestion(conn, sid)["decided_by"] == "Larry"


def test_lead_status_is_validated(conn, mailbox, monkeypatch):
    _read_one(conn, mailbox, monkeypatch)
    lead_id = leads.confirm(conn, int(leads.open_suggestions(conn, mailbox)[0]["id"]), "Larry")
    with pytest.raises(ValueError):
        leads.update_lead(conn, lead_id, "Larry", status="signed")
    leads.update_lead(conn, lead_id, "Larry", status="won", next_step="等 PO")
    lead = leads.list_leads(conn, mailbox)[0]
    assert lead["status"] == "won" and lead["next_step"] == "等 PO"


def test_background_code_has_no_way_to_confirm():
    """结构性保证:确认函数没有默认身份,读数模块里也没有调它的地方。"""
    assert inspect.signature(leads.confirm).parameters["user"].default is inspect.Parameter.empty
    assert "confirm(" not in Path(read_mod.__file__).read_text("utf-8")


def test_api_refuses_confirm_without_identity_and_accepts_tailscale_header(
    conn, mailbox, monkeypatch
):
    _read_one(conn, mailbox, monkeypatch)
    client = TestClient(create_app(conn, mailbox))
    sid = client.get("/api/leads/suggestions").json()[0]["id"]
    assert client.post(f"/api/leads/suggestions/{sid}/confirm").status_code == 401
    ok = client.post(
        f"/api/leads/suggestions/{sid}/confirm",
        headers={"Tailscale-User-Login": "larry@example.test"},
    )
    assert ok.status_code == 200 and ok.json()["confirmed_by"] == "larry@example.test"
    assert client.get("/api/leads").json()[0]["company"] == "Aurora Compute Oy"
    assert client.get("/api/leads/suggestions").json() == []


def test_api_suggestion_and_lead_shapes_match_the_web(conn, mailbox, monkeypatch):
    _read_one(conn, mailbox, monkeypatch, lead={**LEAD, "quoted_numbers": ["48", "99"]})
    client = TestClient(create_app(conn, mailbox))
    s = client.get("/api/leads/suggestions").json()[0]
    assert set(s) >= {
        "id",
        "thread_id",
        "company",
        "contact",
        "wants",
        "quantity",
        "region",
        "priority",
        "model",
        "task_version",
        "produced_at",
        "unverified",
    }
    assert s["unverified"] == ["99"]
    client.post(f"/api/leads/suggestions/{s['id']}/dismiss", headers={"X-User": "Larry"})
    assert client.get("/api/leads/failed").json() == {"count": 0}
    patched = client.patch("/api/leads/999", json={"status": "won"}, headers={"X-User": "Larry"})
    assert patched.status_code == 404
