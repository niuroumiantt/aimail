"""对表的读写,全是参数化 SQL。业务判断(归并规则、分组)不在这里。"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime

from mail2leads.ingest.parse import Parsed


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def ensure_mailbox(conn: sqlite3.Connection, address: str, display_name: str = "") -> int:
    row = conn.execute("SELECT id FROM mailbox WHERE address = ?", (address,)).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO mailbox (address, display_name, created_at) VALUES (?, ?, ?)",
        (address, display_name, now_iso()),
    )
    return int(cur.lastrowid)


def get_cursor(conn: sqlite3.Connection, mailbox_id: int, folder: str) -> tuple[int, int] | None:
    row = conn.execute(
        "SELECT uid_validity, last_uid FROM ingest_cursor WHERE mailbox_id = ? AND folder = ?",
        (mailbox_id, folder),
    ).fetchone()
    return (int(row["uid_validity"]), int(row["last_uid"])) if row else None


def set_cursor(
    conn: sqlite3.Connection, mailbox_id: int, folder: str, uid_validity: int, last_uid: int
) -> None:
    conn.execute(
        "INSERT INTO ingest_cursor (mailbox_id, folder, uid_validity, last_uid) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT (mailbox_id, folder) DO UPDATE SET uid_validity = excluded.uid_validity, "
        "last_uid = excluded.last_uid",
        (mailbox_id, folder, uid_validity, last_uid),
    )


def thread_of_message_id(conn: sqlite3.Connection, mailbox_id: int, message_id: str) -> int | None:
    row = conn.execute(
        "SELECT thread_id FROM message WHERE mailbox_id = ? AND message_id = ?",
        (mailbox_id, message_id),
    ).fetchone()
    return int(row["thread_id"]) if row else None


def raw_seen(conn: sqlite3.Connection, raw_sha256: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM message WHERE raw_sha256 = ?", (raw_sha256,)).fetchone()
        is not None
    )


def find_thread_by_key(
    conn: sqlite3.Connection, mailbox_id: int, subject_key: str, contact_email: str, since: str
) -> int | None:
    row = conn.execute(
        "SELECT id FROM thread WHERE mailbox_id = ? AND subject_key = ? AND contact_email = ? "
        "AND last_at >= ? ORDER BY last_at DESC LIMIT 1",
        (mailbox_id, subject_key, contact_email, since),
    ).fetchone()
    return int(row["id"]) if row else None


def create_thread(
    conn: sqlite3.Connection,
    mailbox_id: int,
    subject: str,
    subject_key: str,
    contact_email: str,
    contact_name: str,
    at: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO thread (mailbox_id, subject, subject_key, contact_email, contact_name, "
        "first_at, last_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (mailbox_id, subject, subject_key, contact_email, contact_name, at, at),
    )
    return int(cur.lastrowid)


def touch_thread(conn: sqlite3.Connection, thread_id: int, at: str) -> None:
    conn.execute(
        "UPDATE thread SET last_at = MAX(last_at, ?) WHERE id = ?",
        (at, thread_id),
    )


def set_folder(conn: sqlite3.Connection, thread_id: int, folder: str) -> None:
    conn.execute("UPDATE thread SET folder = ? WHERE id = ?", (folder, thread_id))


def insert_message(
    conn: sqlite3.Connection,
    mailbox_id: int,
    thread_id: int,
    parsed: Parsed,
    direction: str,
    raw: bytes,
    body_new: str,
    body_quoted: str,
    received_at: str,
) -> int:
    sha = hashlib.sha256(raw).hexdigest()
    cur = conn.execute(
        "INSERT INTO message (mailbox_id, thread_id, message_id, in_reply_to, refs, direction, "
        "from_name, from_email, to_emails, subject, sent_at, received_at, body_new, body_quoted, "
        "raw, raw_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            mailbox_id,
            thread_id,
            parsed.message_id,
            parsed.in_reply_to,
            " ".join(parsed.references),
            direction,
            parsed.from_name,
            parsed.from_email,
            ",".join(parsed.to_emails),
            parsed.subject,
            parsed.sent_at or received_at,
            received_at,
            body_new,
            body_quoted,
            raw,
            sha,
        ),
    )
    message_pk = int(cur.lastrowid)
    for a in parsed.attachments:
        conn.execute(
            "INSERT INTO attachment (message_id, filename, content_type, size, sha256, content) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (message_pk, a.filename, a.content_type, len(a.content), a.sha256, a.content),
        )
    return message_pk


def list_threads(
    conn: sqlite3.Connection, mailbox_id: int, folder: str | None = None
) -> list[sqlite3.Row]:
    sql = "SELECT * FROM thread WHERE mailbox_id = ?"
    args: list[object] = [mailbox_id]
    if folder:
        sql += " AND folder = ?"
        args.append(folder)
    sql += " ORDER BY last_at DESC"
    return conn.execute(sql, args).fetchall()


def get_thread(conn: sqlite3.Connection, thread_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM thread WHERE id = ?", (thread_id,)).fetchone()


def thread_messages(conn: sqlite3.Connection, thread_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, direction, from_name, from_email, to_emails, subject, sent_at, body_new, "
        "body_quoted FROM message WHERE thread_id = ? ORDER BY sent_at, id",
        (thread_id,),
    ).fetchall()


def attachment_names(conn: sqlite3.Connection, message_pk: int) -> list[str]:
    rows = conn.execute(
        "SELECT filename FROM attachment WHERE message_id = ? ORDER BY id", (message_pk,)
    )
    return [str(r["filename"]) for r in rows]


def latest_reading(conn: sqlite3.Connection, message_pk: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM message_reading WHERE source_id = ? "
        "ORDER BY produced_at DESC, id DESC LIMIT 1",
        (message_pk,),
    ).fetchone()
