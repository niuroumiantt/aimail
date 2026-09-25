from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import pytest
from fastapi.testclient import TestClient

from aimail import outreach as o
from aimail.api.app import create_app
from aimail.ingest.run import store_raw
from conftest import make_raw

NOW = datetime(2030, 1, 1, 10, 0, tzinfo=UTC)
PAYLOAD = {
    "schema_version": "1",
    "external_id": "lg_one",
    "idempotency_key": "example.test:initial",
    "company": "Example Colo",
    "website": "https://example.test",
    "email": "support@example.test",
    "country": "US",
    "tier": "1D",
    "policy_version": "v2",
    "source": {"url": "https://example.test/contact"},
    "cadence_days": o.CADENCE,
}
STEPS = [
    {"day": d, "subject": "Supply introduction", "body": f"Approved content day {d}"}
    for d in o.CADENCE
]


class Transport:
    def __init__(self, result="ok", fail=False):
        self.calls = []
        self.result, self.fail = result, fail

    def deliver(self, sender, recipients, raw):
        self.calls.append((sender, recipients, raw))
        if self.fail:
            raise TimeoutError()
        return self.result


@pytest.fixture
def sequence(conn, mailbox):
    o.init(conn)
    return o.import_prospect(conn, mailbox, PAYLOAD)["receipt_id"]


def tick(conn, mailbox, transport, when=NOW, enabled=True):
    return o.tick(
        conn,
        mailbox,
        sender="sales@example.test",
        sender_name="Supplier",
        transport=transport,
        enabled=enabled,
        now=when,
    )


def test_import_never_sends_and_is_idempotent(conn, mailbox, sequence):
    assert o.import_prospect(conn, mailbox, PAYLOAD)["receipt_id"] == sequence
    assert not tick(conn, mailbox, Transport())
    with pytest.raises(ValueError):
        o.import_prospect(conn, mailbox, {**PAYLOAD, "external_id": "second"})
    with pytest.raises(ValueError):
        o.import_prospect(conn, mailbox, {**PAYLOAD, "company": "changed"})


def test_exact_six_day_schedule(conn, mailbox, sequence):
    o.approve(conn, mailbox, sequence, "owner", STEPS, True, NOW)
    t = Transport()
    assert not tick(conn, mailbox, t, enabled=False)
    for day in o.CADENCE:
        if day:
            assert not tick(conn, mailbox, t, NOW + timedelta(days=day, seconds=-1))
        assert tick(conn, mailbox, t, NOW + timedelta(days=day))
        assert not tick(conn, mailbox, t, NOW + timedelta(days=day))
    assert len(t.calls) == 6
    assert o.get(conn, mailbox, sequence)["state"] == "completed"
    assert conn.execute("SELECT COUNT(*) FROM outbound").fetchone()[0] == 6
    assert len(o.events(conn, mailbox)["events"]) == 14


@pytest.mark.parametrize("fail,result", [(True, "ok"), (False, "partial refusal")])
def test_ambiguous_or_refused_does_not_retry(conn, mailbox, sequence, fail, result):
    o.approve(conn, mailbox, sequence, "owner", STEPS, True, NOW)
    t = Transport(result, fail)
    assert not tick(conn, mailbox, t)
    assert o.get(conn, mailbox, sequence)["state"] == "delivery_unknown"
    assert not tick(conn, mailbox, t, NOW + timedelta(days=90))
    assert len(t.calls) == 1
    assert conn.execute("SELECT COUNT(*) FROM outbound").fetchone()[0] == 0


def test_crashed_attempt_is_not_resent(conn, mailbox, sequence):
    o.approve(conn, mailbox, sequence, "owner", STEPS, True, NOW)
    conn.execute("UPDATE prospect_step SET state='sending' WHERE day=0")
    o.recover(conn, mailbox)
    assert o.get(conn, mailbox, sequence)["state"] == "delivery_unknown"
    assert not tick(conn, mailbox, Transport())


@pytest.mark.parametrize("by_reference", [False, True])
def test_any_reply_including_new_sender_stops(conn, mailbox, sequence, by_reference):
    o.approve(conn, mailbox, sequence, "owner", STEPS, True, NOW)
    t = Transport()
    tick(conn, mailbox, t)
    mid = conn.execute("SELECT message_id FROM prospect_step WHERE day=0").fetchone()[0]
    raw = make_raw(
        from_="another@example.test" if by_reference else PAYLOAD["email"],
        in_reply_to=mid if by_reference else "",
        date=NOW + timedelta(days=1),
    )
    store_raw(conn, mailbox, raw, "in", NOW + timedelta(days=1))
    assert not tick(conn, mailbox, t, NOW + timedelta(days=7))
    assert o.get(conn, mailbox, sequence)["state"] == "replied"
    assert len(t.calls) == 1


def test_dsn_stops_even_without_reply_headers(conn, mailbox, sequence):
    o.approve(conn, mailbox, sequence, "owner", STEPS, True, NOW)
    t = Transport()
    tick(conn, mailbox, t)
    report = EmailMessage()
    report["From"] = "mailer-daemon@sender.test"
    report["To"] = "sales@sender.test"
    report["Message-ID"] = "<bounce@sender.test>"
    report.set_type("multipart/report")
    status = EmailMessage()
    status.set_type("message/delivery-status")
    recipient = EmailMessage()
    recipient["Final-Recipient"] = "rfc822; support@example.test"
    recipient["Action"] = "failed"
    recipient["Status"] = "5.1.1"
    status.set_payload([recipient])
    report.attach(status)
    store_raw(conn, mailbox, report.as_bytes(), "in", NOW + timedelta(days=1))
    assert not tick(conn, mailbox, t, NOW + timedelta(days=7))
    assert o.get(conn, mailbox, sequence)["state"] == "bounced"


def test_missed_intervals_do_not_burst(conn, mailbox, sequence):
    o.approve(conn, mailbox, sequence, "owner", STEPS, True, NOW)
    t = Transport()
    tick(conn, mailbox, t)
    assert tick(conn, mailbox, t, NOW + timedelta(days=61))
    assert not tick(conn, mailbox, t, NOW + timedelta(days=61))
    assert len(t.calls) == 2
    assert (
        conn.execute("SELECT state FROM prospect_step WHERE day=7").fetchone()[0] == "skipped_late"
    )


def test_authorization_content_is_immutable(conn, mailbox, sequence):
    with pytest.raises(ValueError):
        o.approve(conn, mailbox, sequence, "owner", STEPS, False, NOW)
    o.approve(conn, mailbox, sequence, "owner", STEPS, True, NOW)
    with pytest.raises(ValueError):
        o.approve(conn, mailbox, sequence, "owner", STEPS, True, NOW)
    conn.execute("UPDATE prospect_step SET body='tampered' WHERE day=7")
    assert not tick(conn, mailbox, Transport())
    assert o.get(conn, mailbox, sequence)["state"] == "paused"


def test_unsubscribe_is_terminal(conn, mailbox, sequence):
    o.approve(conn, mailbox, sequence, "owner", STEPS, True, NOW)
    o.stop(conn, mailbox, sequence, "unsubscribed")
    o.stop(conn, mailbox, sequence, "paused")
    assert o.get(conn, mailbox, sequence)["state"] == "unsubscribed"
    assert not tick(conn, mailbox, Transport())


def test_machine_cannot_approve_and_human_needs_single_use_token(conn, mailbox):
    app = create_app(conn, mailbox, outreach_import_token="private-import-token")
    client = TestClient(app)
    machine = {"Authorization": "Bearer private-import-token"}
    assert client.post("/v1/prospects/import", json=PAYLOAD).status_code == 401
    sid = client.post("/v1/prospects/import", json=PAYLOAD, headers=machine).json()["receipt_id"]
    assert client.post(f"/api/prospects/{sid}/approval-token", headers=machine).status_code == 401
    human = {"X-User": "owner", "X-Outreach-Action": "confirm-v1"}
    assert (
        client.post(
            f"/api/prospects/{sid}/approval-token",
            headers={**human, "Origin": "https://attacker.test"},
        ).status_code
        == 403
    )
    token = client.post(f"/api/prospects/{sid}/approval-token", headers=human).json()["token"]
    body = {"token": token, "steps": STEPS, "policy_confirmed": True}
    assert client.post(f"/api/prospects/{sid}/approve", headers=human, json=body).status_code == 200
    assert client.post(f"/api/prospects/{sid}/approve", headers=human, json=body).status_code == 403
    assert client.get("/v1/outreach/events", headers=machine).json()["next_cursor"] == 2


def test_private_machine_network_cannot_forge_human_proxy_identity(conn, mailbox):
    app = create_app(
        conn,
        mailbox,
        require_oa_auth=True,
        outreach_import_token="private-import-token",
        outreach_approval_proxy_key="proxy-key-not-known-to-importer",
    )
    client = TestClient(app)
    machine = {"Authorization": "Bearer private-import-token"}
    sid = client.post("/v1/prospects/import", json=PAYLOAD, headers=machine).json()["receipt_id"]
    forged = {"X-OA-User": "owner", "X-Outreach-Action": "confirm-v1"}
    assert client.post(f"/api/prospects/{sid}/approval-token", headers=forged).status_code == 403
    assert client.get("/api/prospects", headers=forged).status_code == 403
    trusted = {**forged, "X-Outreach-Approval-Key": "proxy-key-not-known-to-importer"}
    assert client.post(f"/api/prospects/{sid}/approval-token", headers=trusted).status_code == 200


def test_other_sender_cannot_run_or_pause_bound_sequence(conn, mailbox, sequence):
    o.approve(conn, mailbox, sequence, "owner", STEPS, True, NOW)
    t = Transport()
    assert not o.tick(
        conn,
        mailbox,
        sender="different@sender.test",
        sender_name="Supplier",
        transport=t,
        enabled=True,
        now=NOW,
    )
    assert o.get(conn, mailbox, sequence)["state"] == "active"
    assert not t.calls
    # Pre-migration approvals without the new binding still fail closed on a mismatch.
    conn.execute("DELETE FROM prospect_sender WHERE sequence_id=?", (sequence,))
    assert not o.tick(
        conn,
        mailbox,
        sender="different@sender.test",
        sender_name="Supplier",
        transport=t,
        enabled=True,
        now=NOW,
    )
    assert o.get(conn, mailbox, sequence)["state"] == "paused"
    assert not t.calls
