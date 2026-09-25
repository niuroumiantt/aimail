import sqlite3
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


def test_old_reply_attempt_schema_migrates_without_losing_unknown_delivery(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    raw = b"legacy exact message"
    with sqlite3.connect(path) as legacy:
        legacy.executescript("""
        CREATE TABLE mailbox(id INTEGER PRIMARY KEY,address TEXT NOT NULL UNIQUE,
          display_name TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
        INSERT INTO mailbox(id,address,created_at) VALUES(1,'larry@example.test','2026-09-25');
        CREATE TABLE thread(id INTEGER PRIMARY KEY,
          mailbox_id INTEGER NOT NULL REFERENCES mailbox(id),
          subject TEXT NOT NULL,subject_key TEXT NOT NULL,contact_email TEXT NOT NULL,
          contact_name TEXT NOT NULL DEFAULT '',folder TEXT NOT NULL DEFAULT 'inbox',
          first_at TEXT NOT NULL,last_at TEXT NOT NULL);
        INSERT INTO thread(id,mailbox_id,subject,subject_key,contact_email,first_at,last_at)
          VALUES(7,1,'RFQ','rfq','customer@example.test','2026-09-25','2026-09-25');
        CREATE TABLE reply_attempt(
          id INTEGER PRIMARY KEY, thread_id INTEGER NOT NULL REFERENCES thread(id),
          token_hash TEXT NOT NULL UNIQUE, sender TEXT NOT NULL, actor TEXT NOT NULL,
          raw BLOB NOT NULL, state TEXT NOT NULL CHECK(state IN ('sending','unknown','recorded')),
          created_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX reply_unresolved ON reply_attempt(thread_id)
          WHERE state IN ('sending','unknown');
        INSERT INTO reply_attempt VALUES(3,7,'old-token','larry@example.test','larry@example.test',
          X'6c6567616379206578616374206d657373616765','unknown','2026-09-25T00:00:00+00:00');
        """)
    conn = connect(path)
    record = conn.execute("SELECT id,state,raw FROM reply_attempt").fetchone()
    assert (record["id"], record["state"], bytes(record["raw"])) == (3, "unknown", raw)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO reply_attempt(thread_id,token_hash,sender,actor,raw,state,created_at) "
            "VALUES(7,'blocked-token','larry@example.test','larry@example.test',?,'unknown',?)",
            (raw, datetime.now(UTC).isoformat()),
        )
    conn.execute("UPDATE reply_attempt SET state='resolved_not_sent' WHERE id=3")
    conn.execute(
        "INSERT INTO reply_attempt(thread_id,token_hash,sender,actor,raw,state,created_at) "
        "VALUES(7,'new-token','larry@example.test','larry@example.test',?,'sending',?)",
        (raw + b" new", datetime.now(UTC).isoformat()),
    )
    assert conn.execute("SELECT count(*) FROM reply_attempt").fetchone()[0] == 2
    conn.close()
