from datetime import UTC, datetime

import pytest

from aimail.ingest.run import store_raw
from aimail.send import TokenBox, send
from aimail.store import repo
from aimail.store.db import connect
from conftest import make_raw


def test_uncertain_delivery_blocks_new_token_after_restart(tmp_path):
    path = tmp_path / "mail.sqlite3"
    conn = connect(path)
    box = repo.ensure_mailbox(conn, "larry@glocalstorage.com")
    pk, _ = store_raw(conn, box, make_raw(), "in", datetime.now(UTC))
    tid = conn.execute("SELECT thread_id FROM message WHERE id=?", (pk,)).fetchone()[0]
    calls = []

    class InterruptedTransport:
        def deliver(self, sender, recipients, raw):
            calls.append(raw)
            raise TimeoutError("private server response")

    def attempt(c):
        send(
            c,
            token=TokenBox().mint(tid, "larry"),
            mailbox_id=box,
            sender="larry@glocalstorage.com",
            sender_name="Larry",
            thread_id=tid,
            to=["customer@example.test"],
            subject="Re: RFQ",
            body="Hello",
            transport=InterruptedTransport(),
        )

    with pytest.raises(ValueError, match="发送结果待核对") as error:
        attempt(conn)
    assert "private" not in str(error.value)
    record = conn.execute("SELECT * FROM reply_attempt").fetchone()
    assert record["state"] == "unknown" and bytes(record["raw"]) == calls[0]
    conn.close()
    conn = connect(path)
    with pytest.raises(ValueError, match="待核对"):
        attempt(conn)
    assert len(calls) == 1
    assert conn.execute("SELECT count(*) FROM outbound").fetchone()[0] == 0
    conn.close()
