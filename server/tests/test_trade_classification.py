"""Contract and storage checks, not an estimate of real-model accuracy."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from aimail import backends, reclassify
from aimail.api.app import create_app
from aimail.ingest.run import store_raw
from aimail.store import mail_state, repo
from aimail.tasks import read as read_task
from aimail.tasks.summarize import TASK_VERSION, InquirySummary
from conftest import make_raw

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def incoming(conn, mailbox, identity: str, *, body="Original mail", reply_to="", direction="in"):
    pk, _ = store_raw(
        conn,
        mailbox,
        make_raw(message_id=f"<{identity}@trade.test>", body=body, in_reply_to=reply_to),
        direction,
        NOW,
        new_thread=not reply_to,
    )
    return int(pk)


def seed(conn, source: int, payload: dict, version="summarize_inquiry@4", status="ok"):
    conn.execute(
        "INSERT INTO message_reading(source_id,model,task_version,produced_at,status,payload) "
        "VALUES(?,'test model',?,?,?,?)",
        (source, version, NOW.isoformat(), status, json.dumps(payload)),
    )


@pytest.mark.parametrize("role", ["supplier", "transaction"])
def test_broad_trade_reading_does_not_create_purchaser_suggestion(conn, mailbox, monkeypatch, role):
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL", "test")
    payload = {
        "is_inquiry": False,
        "is_trade": True,
        "trade_role": role,
        "mail_type": "business",
        "detected_language": "en",
        "summary_zh": "供应商提供 DDR5 现货。",
        "summary_en": "DDR5 stock offer.",
        "facts": ["DDR5 available"],
        "quoted_numbers": ["DDR5"],
    }
    calls = []

    def complete(*args):
        calls.append(args)
        return json.dumps(payload)

    monkeypatch.setattr(backends, "_call_local", complete)
    pk = incoming(conn, mailbox, role, body="Original DDR5 available stock offer")
    assert read_task.read_message(conn, pk, NOW) == "ok"
    reading = repo.latest_reading(conn, pk)
    stored = json.loads(reading["payload"])
    assert stored["is_trade"] is True and stored["trade_role"] == role
    assert stored["unverified"] == [] and reading["task_version"] == TASK_VERSION
    assert len(calls) == 1
    assert conn.execute("SELECT count(*) FROM lead_suggestion").fetchone()[0] == 0
    assert TestClient(create_app(conn, mailbox)).get("/api/threads").json()[0]["has_trade"] is True


def test_explicit_non_trade_corrects_legacy_business_and_preserves_original(conn, mailbox):
    pk = incoming(conn, mailbox, "billing", body="Original periodic AR aging statement")
    seed(conn, pk, {"is_inquiry": False, "mail_type": "business"})
    client = TestClient(create_app(conn, mailbox))
    assert client.get("/api/threads").json()[0]["has_trade"] is True  # legacy compatibility
    original = tuple(conn.execute("SELECT raw FROM message WHERE id=?", (pk,)).fetchone())
    seed(
        conn,
        pk,
        {"is_inquiry": False, "is_trade": False, "trade_role": "none", "mail_type": "billing"},
        TASK_VERSION,
    )
    assert client.get("/api/threads").json()[0]["has_trade"] is False
    assert tuple(conn.execute("SELECT raw FROM message WHERE id=?", (pk,)).fetchone()) == original
    assert (
        conn.execute("SELECT count(*) FROM message_reading WHERE source_id=?", (pk,)).fetchone()[0]
        == 2
    )


def test_reclassification_inspection_never_calls_models_and_scope_is_bounded(
    conn, mailbox, monkeypatch
):
    other = repo.ensure_mailbox(conn, "other@example.test")
    first = incoming(conn, mailbox, "old")
    latest = incoming(conn, mailbox, "latest", reply_to="<old@trade.test>")
    outgoing = incoming(conn, mailbox, "outgoing", direction="out")
    other_pk = incoming(conn, other, "other")
    seed(conn, first, {"is_inquiry": False})
    seed(conn, latest, {"is_inquiry": False})
    hidden = incoming(conn, mailbox, "hidden")
    hidden_thread = conn.execute("SELECT thread_id FROM message WHERE id=?", (hidden,)).fetchone()[
        0
    ]
    mail_state.change(conn, hidden_thread, "trash", "operator")
    monkeypatch.setattr(
        reclassify, "read_message", lambda *args, **kw: pytest.fail("dry run called model")
    )
    result = reclassify.run_batch(conn, mailbox, limit=1)
    assert result["eligible"] == 1 and result["processed"] == 0
    assert {item["source_id"] for item in result["selected"]} == {latest}
    assert not {first, outgoing, other_pk, hidden} & {
        item["source_id"] for item in result["selected"]
    }


def test_reclassification_skips_current_attempts_and_requires_explicit_retry(
    conn, mailbox, monkeypatch
):
    succeeded = incoming(conn, mailbox, "current")
    failed = incoming(conn, mailbox, "failed")
    stale = incoming(conn, mailbox, "stale")
    seed(conn, succeeded, {"is_inquiry": False}, TASK_VERSION)
    seed(conn, failed, {}, TASK_VERSION, "failed")
    seed(conn, stale, {"is_inquiry": False}, "summarize_inquiry@3")
    calls = []
    monkeypatch.setattr(backends, "ready", lambda: (True, "test"))

    def read(conn, pk, **kw):
        calls.append((pk, kw["tasks"]))
        seed(conn, pk, {"is_inquiry": False, "is_trade": False}, TASK_VERSION)
        return "ok"

    monkeypatch.setattr(reclassify, "read_message", read)
    result = reclassify.run_batch(conn, mailbox, apply=True)
    assert result["processed"] == 1 and calls == [(stale, frozenset({"read"}))]
    assert reclassify.run_batch(conn, mailbox, apply=True)["processed"] == 0
    assert reclassify.run_batch(conn, mailbox, apply=True, retry_failed=True)["processed"] == 1
    assert calls[-1][0] == failed
    with pytest.raises(ValueError):
        reclassify.run_batch(conn, mailbox, limit=101)


def test_new_trade_contract_cannot_omit_or_contradict_trade_fields():
    base = {
        "is_inquiry": True,
        "mail_type": "inquiry",
        "detected_language": "en",
        "summary_zh": "采购",
        "summary_en": "Purchase",
        "facts": [],
        "quoted_numbers": [],
    }
    with pytest.raises(ValidationError):
        InquirySummary.model_validate(base)
    with pytest.raises(ValidationError):
        InquirySummary.model_validate({**base, "is_trade": False, "trade_role": "none"})
    with pytest.raises(ValidationError):
        InquirySummary.model_validate({**base, "is_trade": True, "trade_role": "none"})
