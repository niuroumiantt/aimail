"""Forward preserves MIME and sender/token protections without changing the source."""

from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser

import pytest
from fastapi.testclient import TestClient

from aimail import send
from aimail.api.app import create_app
from aimail.ingest.run import store_raw
from aimail.send.reconcile import resolve
from conftest import make_raw
from test_send import FakeTransport

NOW = datetime(2026, 10, 10, tzinfo=UTC)


def seed(conn, mailbox):
    original = BytesParser(policy=policy.default).parsebytes(
        make_raw(
            html=(
                "<p>Exact sentence.</p><table><tr><td>Model A</td><td>48</td></tr></table>"
                '<img src="cid:logo">'
            ),
            body="Exact sentence. Model A 48",
            attachments=[("报价.pdf", b"%PDF-original", "application/pdf")],
        )
    )
    original.get_body(preferencelist=("html",)).add_related(
        b"image-bytes",
        maintype="image",
        subtype="png",
        cid="<logo>",
        filename="logo.png",
        disposition="inline",
    )
    raw = original.as_bytes()
    pk, _ = store_raw(conn, mailbox, raw, "in", NOW)
    tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    return pk, tid, raw


def forward(conn, mailbox, pk, tid, transport, **kwargs):
    return send.send(
        conn,
        token=send.TokenBox().mint(tid, "Larry"),
        mailbox_id=mailbox,
        sender="larry@example.test",
        sender_name="Larry",
        thread_id=tid,
        to=["colleague@example.test"],
        subject="Fwd: RFQ",
        body="Please review.",
        transport=transport,
        now=NOW,
        forward_message_id=pk,
        **kwargs,
    )


def test_forward_preserves_html_inline_and_attachments_in_separate_thread(conn, mailbox):
    pk, tid, raw = seed(conn, mailbox)
    smtp = FakeTransport()
    forward(conn, mailbox, pk, tid, smtp)
    msg = BytesParser(policy=policy.default).parsebytes(smtp.sent[0][2])
    assert msg["To"] == "colleague@example.test"
    assert not msg["In-Reply-To"] and not msg["References"]
    assert (
        "<table><tr><td>Model A</td><td>48</td></tr></table>"
        in msg.get_body(preferencelist=("html",)).get_content()
    )
    assert "Please review." in msg.get_body(preferencelist=("plain",)).get_content()
    parts = list(msg.walk())
    assert any(
        p["Content-ID"] == "<logo>" and p.get_payload(decode=True) == b"image-bytes" for p in parts
    )
    assert any(
        p.get_filename() == "报价.pdf" and p.get_payload(decode=True) == b"%PDF-original"
        for p in parts
    )
    assert bytes(conn.execute("SELECT raw FROM message WHERE id=?", (pk,)).fetchone()[0]) == raw
    assert conn.execute("SELECT folder FROM thread WHERE id=?", (tid,)).fetchone()[0] == "inbox"
    sent = conn.execute(
        "SELECT o.thread_id,m.thread_id AS mt FROM outbound o JOIN message m ON m.id=o.message_pk"
    ).fetchone()
    assert sent["thread_id"] == sent["mt"] != tid


def test_forward_attachment_opt_out_keeps_inline_body(conn, mailbox):
    pk, tid, _ = seed(conn, mailbox)
    smtp = FakeTransport()
    forward(conn, mailbox, pk, tid, smtp, include_attachments=False)
    msg = BytesParser(policy=policy.default).parsebytes(smtp.sent[0][2])
    assert not any(p.get_filename() == "报价.pdf" for p in msg.walk())
    assert any(p["Content-ID"] == "<logo>" for p in msg.walk())


def test_unknown_forward_remains_locked_and_reconciles_without_reply_status(conn, mailbox):
    class Unknown(FakeTransport):
        def deliver(self, *args):
            super().deliver(*args)
            raise TimeoutError

    pk, tid, _ = seed(conn, mailbox)
    smtp = Unknown()
    with pytest.raises(ValueError, match="待核对"):
        forward(conn, mailbox, pk, tid, smtp)
    with pytest.raises(ValueError, match="勿重复"):
        forward(conn, mailbox, pk, tid, smtp)
    assert len(smtp.sent) == 1
    attempt = conn.execute("SELECT id FROM reply_attempt").fetchone()[0]
    result = resolve(
        conn,
        thread_id=tid,
        attempt_id=attempt,
        actor="Larry",
        outcome="sent",
        evidence_reference="provider-sent-record-123",
        now=NOW,
    )
    assert result["ok"]
    assert conn.execute("SELECT folder FROM thread WHERE id=?", (tid,)).fetchone()[0] == "inbox"
    assert conn.execute("SELECT thread_id FROM outbound").fetchone()[0] != tid
    assert resolve(
        conn,
        thread_id=tid,
        attempt_id=attempt,
        actor="Larry",
        outcome="sent",
        evidence_reference="provider-sent-record-123",
        now=NOW,
    )["already_resolved"]


def test_forward_api_validates_source_and_single_use_token(conn, mailbox):
    pk, tid, _ = seed(conn, mailbox)
    smtp = FakeTransport()
    with TestClient(
        create_app(conn, mailbox, sender="larry@example.test", transport=smtp)
    ) as client:
        headers = {"X-User": "Larry"}
        token = client.post(f"/api/threads/{tid}/send-token", headers=headers).json()["token"]
        payload = {
            "token": token,
            "to": ["colleague@example.test"],
            "subject": "Fwd: RFQ",
            "body": "",
            "forward_message_id": pk + 99,
        }
        assert (
            client.post(f"/api/threads/{tid}/send", headers=headers, json=payload).status_code
            == 422
        )
        assert not smtp.sent
        payload.update(
            token=client.post(f"/api/threads/{tid}/send-token", headers=headers).json()["token"],
            forward_message_id=pk,
        )
        assert (
            client.post(f"/api/threads/{tid}/send", headers=headers, json=payload).status_code
            == 200
        )
        assert (
            client.post(f"/api/threads/{tid}/send", headers=headers, json=payload).status_code
            == 403
        )
        assert len(smtp.sent) == 1
