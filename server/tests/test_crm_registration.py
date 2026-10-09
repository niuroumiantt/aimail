"""Registration preserves originals, mailbox isolation and acknowledged facts."""

import json
import sqlite3
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from aimail.api.app import create_app
from aimail.ingest.run import store_raw
from aimail.store import crm, repo
from aimail.tasks.register_contact import Citation, Extraction, Fields, checked
from conftest import make_raw


def seed(conn, mailbox):
    raw = make_raw(body="I'm Alex from Aurora. Please quote 12 DDR5 modules.")
    pk, _ = store_raw(conn, mailbox, raw, "in", datetime.now(UTC))
    return conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]


def test_confirm_receipt_scope_retry_and_immutable_original(conn, mailbox):
    tid = seed(conn, mailbox)
    before = [tuple(r) for r in conn.execute("SELECT * FROM message")]
    private = repo.ensure_mailbox(conn, "private@example.test")
    other = store_raw(
        conn, private, make_raw(message_id="<private@test>"), "in", datetime.now(UTC)
    )[0]
    other_tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (other,)).fetchone()[0]
    app = create_app(
        conn,
        mailbox,
        require_oa_auth=True,
        mailbox_access={"owner@example.test": ("sales@example.test",)},
        outreach_import_token="machine-test",
    )
    person = {"X-OA-Email": "owner@example.test", "X-OA-User": "owner"}
    machine = {"Authorization": "Bearer machine-test"}
    fields = crm.Registration(
        email="ALEX@aurora.test", company="Aurora", quantity="12"
    ).model_dump()
    with TestClient(app) as client:
        url = f"/api/threads/{tid}/registration"
        assert client.post(url, json=fields).status_code == 401
        assert (
            client.get(f"/api/threads/{other_tid}/registration", headers=person).status_code == 404
        )
        assert client.get("/v1/contact-registrations", headers=person).status_code == 401
        assert (
            client.post(
                url, json=fields, headers={**person, "Origin": "https://evil.test"}
            ).status_code
            == 403
        )
        saved = client.post(url, json=fields, headers=person)
        assert saved.status_code == 200
        assert saved.json()["registration"]["receipt"] == {}
        assert client.post(url, json=fields, headers=person).json() == saved.json()
        assert (
            client.post(url, json={**fields, "company": "Changed"}, headers=person).status_code
            == 409
        )
        feed = client.get("/v1/contact-registrations", headers=machine).json()
        assert len(feed["items"]) == 1
        item = feed["items"][0]
        assert item["fields"]["email"] == "alex@aurora.test"
        assert item["confirmed_by"] == "owner@example.test"
        assert item["source"]["thread_id"] == str(tid)
        assert "body_new" not in json.dumps(item)
        receipt = {
            "fingerprint": item["fingerprint"],
            "account_id": "account_1",
            "company_id": "company_1",
        }
        receipt_url = f"/v1/contact-registrations/{item['id']}/receipt"
        assert (
            client.post(
                receipt_url, json={**receipt, "fingerprint": "0" * 64}, headers=machine
            ).status_code
            == 409
        )
        assert client.post(receipt_url, json=receipt, headers=machine).status_code == 200
        assert client.post(receipt_url, json=receipt, headers=machine).status_code == 200
        assert (
            client.post(
                receipt_url, json={**receipt, "account_id": "wrong"}, headers=machine
            ).status_code
            == 409
        )
        assert client.get(url, headers=person).json()["registration"]["receipt"] == receipt
        assert (
            client.get(
                "/v1/contact-registrations", params={"after": item["id"]}, headers=machine
            ).json()["items"]
            == []
        )
    assert [
        tuple(r) for r in conn.execute("SELECT * FROM message WHERE mailbox_id=?", (mailbox,))
    ] == before
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute("DELETE FROM crm_registration")


def test_unconfigured_never_claims_success_and_invalid_facts_rejected(conn, mailbox):
    tid = seed(conn, mailbox)
    with TestClient(create_app(conn, mailbox)) as client:
        url = f"/api/threads/{tid}/registration"
        assert (
            client.post(url, json={"email": "a@test"}, headers={"X-User": "operator"}).status_code
            == 503
        )
        assert (
            client.post(
                url,
                json={"email": "a@test", "website": "javascript:alert(1)"},
                headers={"X-User": "operator"},
            ).status_code
            == 422
        )
        assert (
            client.post(
                url,
                json={"email": "a@test", "due_at": "2026-02-31"},
                headers={"X-User": "operator"},
            ).status_code
            == 422
        )
        assert client.get(url).json()["defaults"]["company"] == ""
    assert conn.execute("SELECT count(*) FROM crm_registration").fetchone()[0] == 0


def test_model_requires_original_citations_and_numbers():
    source = "Alex from Aurora asks for 12 DDR5 modules."
    value = Extraction(
        fields=Fields(company="Aurora", contact="Invented", quantity="99", wants="12 件 DDR5内存"),
        citations=[
            Citation(field="company", source_id=1, quote=source),
            Citation(field="contact", source_id=1, quote=source),
            Citation(field="quantity", source_id=1, quote=source),
            Citation(field="wants", source_id=1, quote=source),
        ],
    )
    result = checked(value, [{"id": 1, "text": source}])
    assert result["fields"]["company"] == "Aurora"
    assert result["fields"]["contact"] == result["fields"]["quantity"] == ""
    assert result["fields"]["wants"] == "12 件 DDR5内存"
    assert len(result["warnings"]) == 2


def test_explicit_model_extraction_attribution_staleness_and_no_automatic_facts(
    tmp_path, monkeypatch
):
    import time

    from aimail import backends
    from aimail.store.db import connect

    conn = connect(tmp_path / "mail.db")
    mailbox = repo.ensure_mailbox(conn, "sales@example.test")
    tid = seed(conn, mailbox)
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL", "fixture")
    calls = []

    def complete(system, source, shape):
        calls.append(source)
        return Extraction(
            fields=Fields(company="Aurora"),
            citations=[Citation(field="company", source_id=1, quote="Alex from Aurora")],
        )

    monkeypatch.setattr(backends, "complete", complete)
    with TestClient(create_app(conn, mailbox, outreach_import_token="test")) as client:
        url = f"/api/threads/{tid}/registration"
        assert client.get(url).json()["suggestion"] is None and not calls
        assert client.post(url + "/extract", headers={"X-User": "operator"}).status_code == 200
        for _ in range(100):
            state = client.get(url).json()
            if state["suggestion"]["status"] != "running":
                break
            time.sleep(0.02)
        suggestion = state["suggestion"]
        assert suggestion["status"] == "ok" and suggestion["fields"]["company"] == "Aurora"
        assert suggestion["source_id"] == 1 and suggestion["task_version"] == "register_contact@1"
        assert suggestion["model"] and suggestion["produced_at"] and not suggestion["stale"]
        assert state["registration"] is None and len(calls) == 1
        store_raw(
            conn,
            mailbox,
            make_raw(message_id="<new@test>", in_reply_to="<a@aurora.test>", body="New message"),
            "in",
            datetime.now(UTC),
            target_thread_id=tid,
        )
        assert client.get(url).json()["suggestion"]["stale"]
    conn.close()
