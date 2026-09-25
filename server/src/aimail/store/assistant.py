"""Append-only, mailbox-scoped audit storage for the production AI reading panel."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime


def append(
    conn: sqlite3.Connection,
    mailbox_id: int,
    kind: str,
    turn_id: str,
    actor: str,
    payload: dict,
) -> None:
    conn.execute(
        "INSERT INTO mailbox_assistant_event(mailbox_id,at,kind,turn_id,actor,payload) "
        "VALUES(?,?,?,?,?,?)",
        (
            mailbox_id,
            datetime.now(UTC).isoformat(),
            kind,
            turn_id,
            actor,
            json.dumps(payload, ensure_ascii=False),
        ),
    )


def conversation(conn: sqlite3.Connection, mailbox_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM mailbox_assistant_event WHERE mailbox_id=? AND id>"
        "COALESCE((SELECT MAX(id) FROM mailbox_assistant_event "
        "WHERE mailbox_id=? AND kind='clear'),0) ORDER BY id",
        (mailbox_id, mailbox_id),
    ).fetchall()
    turns: dict[str, dict] = {}
    for row in rows:
        payload = json.loads(row["payload"])
        if row["kind"] == "question":
            turns[row["turn_id"]] = {
                "id": row["turn_id"],
                "at": row["at"],
                "status": "running",
                **payload,
            }
        elif row["turn_id"] in turns:
            turns[row["turn_id"]].update(payload)
    return list(turns.values())
