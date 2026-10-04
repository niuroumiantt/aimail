"""Incoming mail uses its mailbox route, even when the process default is offline."""

from datetime import UTC, datetime
from types import SimpleNamespace

from aimail import __main__ as main_module
from aimail import backends
from aimail.ingest.run import store_raw
from aimail.store import model_selection, repo
from conftest import make_raw


def test_ingest_checks_the_mailbox_route_and_keeps_other_mailboxes_separate(
    conn, mailbox, monkeypatch
):
    monkeypatch.setenv("LLM_BACKEND", "local")
    monkeypatch.delenv("LOCAL_MODEL", raising=False)
    other = repo.ensure_mailbox(conn, "second@example.test")
    incoming = []
    for mid, provider in ((mailbox, "codex_cli"), (other, "claude_code_cli")):
        model_selection.choose(conn, mid, provider, "operator")
        pk, _ = store_raw(
            conn,
            mid,
            make_raw(message_id=f"<{mid}@example.test>"),
            "in",
            datetime.now(UTC),
        )
        incoming.append((pk, provider))
    monkeypatch.setattr(backends, "ready", lambda: (backends.backend() != "local", ""))
    calls = []
    monkeypatch.setattr(
        main_module,
        "read_message",
        lambda db, pk, **kw: calls.append((pk, backends.backend(), kw["backend"])),
    )
    callback = main_module._reader(SimpleNamespace(tasks=frozenset({"read"})))
    for pk, _ in incoming:
        callback(conn, pk)
    assert calls == [(pk, provider, provider) for pk, provider in incoming]
    assert backends.backend() == "local"


def test_unconnected_selected_backend_keeps_the_original_without_a_fake_reading(
    conn, mailbox, monkeypatch
):
    model_selection.choose(conn, mailbox, "codex_cli", "operator")
    pk, _ = store_raw(conn, mailbox, make_raw(), "in", datetime.now(UTC))
    monkeypatch.setattr(backends, "ready", lambda: (False, "not connected"))
    monkeypatch.setattr(
        main_module, "read_message", lambda *args, **kw: (_ for _ in ()).throw(AssertionError())
    )
    assert main_module._reader(SimpleNamespace(tasks=frozenset({"read"})))(conn, pk) is None
    assert repo.latest_reading(conn, pk) is None
    assert conn.execute("SELECT raw FROM message WHERE id=?", (pk,)).fetchone()["raw"]
