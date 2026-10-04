"""Mailbox routing preferences with task-local, immutable provider snapshots."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from aimail import backends

SELECTABLE = frozenset({"local", "codex_cli", "claude_code_cli"})


def selected(conn: sqlite3.Connection, mailbox_id: int) -> str:
    row = conn.execute(
        "SELECT backend FROM mailbox_model_selection WHERE mailbox_id=?", (mailbox_id,)
    ).fetchone()
    if row:
        return str(row["backend"])
    # Preserve existing deployments until an operator selects a route. Read
    # the configured default, not an outer task's temporary ContextVar value.
    return os.environ.get("LLM_BACKEND", "local").strip().lower()


def choose(conn: sqlite3.Connection, mailbox_id: int, backend: str, actor: str) -> None:
    if backend not in SELECTABLE:
        raise ValueError("不支持这个模型后端")
    if not actor.strip():
        raise PermissionError("模型选择需要操作人")
    conn.execute(
        "INSERT INTO mailbox_model_selection(mailbox_id,backend,selected_by,selected_at) "
        "VALUES(?,?,?,?) ON CONFLICT(mailbox_id) DO UPDATE SET "
        "backend=excluded.backend,selected_by=excluded.selected_by,selected_at=excluded.selected_at",
        (mailbox_id, backend, actor.strip(), datetime.now(UTC).isoformat()),
    )


@contextmanager
def use(
    conn: sqlite3.Connection,
    mailbox_id: int,
    *,
    backend: str | None = None,
    model: str | None = None,
) -> Iterator[str]:
    """Capture once; a selection change cannot relabel an in-flight task."""
    snapshot = selected(conn, mailbox_id) if backend is None else backend
    with backends.use_backend(snapshot, model=model):
        yield snapshot


def state(conn: sqlite3.Connection, mailbox_id: int) -> dict:
    choice = selected(conn, mailbox_id)
    options = backends.provider_catalog()
    with use(conn, mailbox_id, backend=choice):
        model = backends.describe()
    return {"selected": choice, "model": model, "options": options}
